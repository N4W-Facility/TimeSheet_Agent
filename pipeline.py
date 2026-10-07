# ============================================================
# PIPELINE GUIADO
# Pasos fijos en Python. Toda interacción (logs, decisiones,
# aprobaciones) sale por callbacks → la misma lógica sirve
# para la CLI y el agente del chat.
#
# Periodos (regla TNC):
#   Workday → mes calendario (día 1 → último día)
#   N4W     → semanas completas lunes–domingo (1..n)
# Cada paso recibe su periodo; los archivos llevan el rango en el nombre.
# ============================================================
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, List, Optional

import pandas as pd

import config
from core import analysis, database, n4w, outlook, prorate, timesheet
from core.utils import get_date_columns


@dataclass
class Decision:
    """Pregunta que el pipeline no puede resolver solo."""
    kind: str                 # 'prorate_targets', 'n4w_weeks', 'add_projects', ...
    question: str
    options: List[str]
    multi: bool = False       # True → se esperan varias opciones
    context: dict = field(default_factory=dict)
    preselected: List[str] = field(default_factory=list)   # marcadas al abrir (multi)


@dataclass
class Callbacks:
    log: Callable[[str], None] = print
    # (Decision) → str | list[str] | None (None = cancelar)
    decide: Callable[[Decision], object] = lambda d: d.options if d.multi else d.options[0]
    # (título, detalle) → bool
    approve: Callable[[str, str], bool] = lambda title, detail: False


class Cancelled(Exception):
    pass


class _CallbackHandler(logging.Handler):
    def __init__(self, fn):
        super().__init__(logging.INFO)
        self.fn = fn

    def emit(self, record):
        self.fn(record.getMessage())


def _fmt(d: datetime) -> str:
    return d.strftime('%Y-%m-%d')


class Pipeline:
    """Cada método público es un paso independiente (el agente los encadena)."""

    def __init__(self, workdir: Optional[str] = None, email: Optional[str] = None,
                 callbacks: Optional[Callbacks] = None):
        self.workdir = os.path.abspath(workdir or config.WORK_DIR)
        os.makedirs(self.workdir, exist_ok=True)
        self.email = email
        self.cb = callbacks or Callbacks()
        self.task_details_path = self._path(config.N4W_TASK_DETAILS_NAME)

        core_log = logging.getLogger("core")
        core_log.handlers = [_CallbackHandler(self.cb.log)]
        core_log.setLevel(logging.INFO)
        core_log.propagate = False

    def _path(self, name: str, start: datetime = None, end: datetime = None) -> str:
        if start is not None:
            name = name.format(start=_fmt(start), end=_fmt(end))
        return os.path.join(self.workdir, name)

    def _approve(self, title: str, detail: str):
        if not self.cb.approve(title, detail):
            raise Cancelled(f"Cancelled by user: {title}")

    def _ensure_task_details(self):
        if not os.path.exists(self.task_details_path):
            self.cb.log("Downloading N4W codes from Box...")
            database.download_box_file(config.BOX_URL, self.task_details_path)

    def refresh_task_details(self) -> tuple:
        """
        Descarga la base global (N4W_Task_Details) de Box. Sin red usa la copia local.
        Returns: (descargado_ahora, fecha 'YYYY-MM-DD HH:MM' de la copia usada)
        """
        fresh = True
        try:
            self.cb.log("Downloading N4W codes from Box...")
            database.download_box_file(config.BOX_URL, self.task_details_path)
        except Exception as e:
            if not os.path.exists(self.task_details_path):
                raise
            self.cb.log(f"  Box download failed ({e}); using the local copy")
            fresh = False
        when = datetime.fromtimestamp(os.path.getmtime(self.task_details_path))
        return fresh, f"{when:%Y-%m-%d %H:%M}"

    def task_status(self) -> dict:
        """Estado global por código (activo / cerrado / sin abrir, prorrateable, nombres)."""
        self._ensure_task_details()
        return database.task_status(self.task_details_path)

    def catalog(self) -> pd.DataFrame:
        """Todos los códigos conocidos: base global + internos XX."""
        self._ensure_task_details()
        return database.catalog(self.task_details_path)

    # ── Categorías de Outlook ────────────────────────────────
    def create_categories(self, codes: List[str]) -> List[str]:
        """Crea las categorías 'CODE | Descripción' que falten. Devuelve las creadas."""
        cat = self.catalog().set_index('Code')
        created = []
        for code in codes:
            if code not in cat.index:
                continue
            name = cat.loc[code, 'Category']
            if outlook.add_category(name):
                created.append(name)
        return created

    # ── Outlook → timesheet ──────────────────────────────────
    def build_timesheet(self, start: datetime, end: datetime, save_files: bool = True) -> dict:
        """
        Genera 01-Report y 02-Timesheet del rango [start, end].
        save_files=False: solo lee (carga de historial), no escribe archivos.
        Returns: {'path', 'timesheet', 'start', 'end', 'summary', 'unmapped', 'irregular_days'}
        """
        if start > end:
            raise ValueError("Start date is after end date.")
        self.cb.log(f"Reading Outlook {_fmt(start)} → {_fmt(end)}...")
        meetings = outlook.read_meetings(start, end + timedelta(days=1))
        if meetings.empty:
            raise ValueError("Outlook returned no meetings for this period.")

        ts, unmapped = outlook.build_timesheet(meetings, start, end, self.catalog())

        path = self._path(config.TIMESHEET_NAME, start, end)
        if save_files:
            meetings.to_excel(self._path(config.REPORT_NAME, start, end))
            ts.to_csv(path, index_label='Code')
            self.cb.log(f"✓ {os.path.basename(path)}: {len(ts)} codes")

        df = ts.reset_index()
        findings = {
            'path': path if save_files else None,
            'timesheet': df,
            'start': start,
            'end': end,
            'summary': timesheet.summarize(df),
            'unmapped': unmapped,
            'irregular_days': timesheet.find_irregular_days(df),
        }
        for cat, h in unmapped.items():
            self.cb.log(f"  ⚠ Category without code (dropped): '{cat}' — {h:g} h")
        for d in findings['irregular_days']:
            self.cb.log(f"  ⚠ {d['date']}: {d['hours']:g} h ({d['issue']})")
        return findings

    # ── Prorrateo (obligatorio para Workday si hay proyectos Prorate=1) ──
    def virtual_projects(self, csv_path: str) -> List[str]:
        """Códigos con horas marcados Prorate=1 en N4W_Task_Details (deben prorratearse)."""
        self._ensure_task_details()
        df = prorate.classify_projects(pd.read_csv(csv_path), self.task_details_path)
        hours = df[get_date_columns(df)].sum(axis=1)
        return df.loc[(df['Prorate'] == 1) & (hours > 0), 'Code'].astype(str).tolist()

    def prorate(self, csv_path: str, start: datetime, end: datetime) -> str:
        """Reparte horas virtuales → 03-Timesheet_Prorate. Devuelve la ruta."""
        self._ensure_task_details()
        ts = pd.read_csv(csv_path)
        virtual = self.virtual_projects(csv_path)
        candidates = prorate.real_projects(ts, self.task_details_path)
        balance = analysis.by_project(analysis.to_long(ts))
        labels = {f"{c} — {str(balance['Task Name'].get(c, ''))[:30]} "
                  f"({analysis.h(balance['Hours'].get(c, 0.0))} h)": c for c in candidates}
        selected = self.cb.decide(Decision(
            kind='prorate_targets',
            question=(f"Prorate {', '.join(virtual)}: which projects should receive "
                      "those hours? (proportional to their hours)"),
            options=list(labels), multi=True,
            context={'virtual': virtual},
        ))
        if selected is None:
            raise Cancelled("Prorate cancelled")
        chosen = {labels[s] for s in selected}
        selections = {c: c in chosen for c in candidates}

        result = prorate.redistribute(ts, self.task_details_path, selections, self.catalog())
        self._approve("Prorated hours — use them for Workday?",
                      analysis.prorate_comparison(ts, result, virtual))

        path = self._path(config.PRORATE_NAME, start, end)
        result.to_csv(path, index=False)
        self.cb.log(f"✓ {os.path.basename(path)}")
        return path

    # ── Workday ──────────────────────────────────────────────
    def fill_workday(self, csv_path: str, confirm_each_week: bool = True):
        """
        Requiere Chrome con CDP, sesión iniciada y la tabla
        'Enter Time by Type' de la PRIMERA semana abierta.
        """
        from core.workday.automation import WorkdayAutomation
        from core.workday.browser_launcher import is_cdp_running, launch_chrome
        from core.workday.csv_reader import parse_csv

        weeks = parse_csv(csv_path)
        self.cb.log(f"{len(weeks)} weeks | {sum(len(p) for p in weeks.values())} entries")

        if not is_cdp_running() and not launch_chrome(log_callback=self.cb.log):
            raise RuntimeError("Could not open Chrome with remote debugging.")
        self._approve(
            "Workday ready?",
            "1. Sign in to Workday in the Chrome window that just opened.\n"
            "2. Open 'Enter Time by Type' ('Introducción de horas por tipo') for the week starting "
            f"{next(iter(weeks))} (Sunday).\n\nApprove when the table is visible.")

        confirm = ((lambda msg: self.cb.approve("Save this week?", msg))
                   if confirm_each_week else (lambda msg: True))
        auto = WorkdayAutomation(log_callback=self.cb.log, confirm_callback=confirm)
        try:
            auto.connect()
            auto.detect_lang()
            auto.run(weeks)
        finally:
            auto.close()

    # ── N4W Facility ─────────────────────────────────────────
    def submit_n4w(self, csv_path: str, start: datetime, end: datetime) -> str:
        """Valida, genera el Excel N4W y lo copia a OneDrive. Devuelve la ruta destino."""
        if not self.email:
            raise ValueError("User email is required for N4W.")
        df = pd.read_csv(csv_path)

        ok, err = timesheet.validate_complete_weeks(start, end)
        if not ok:
            raise ValueError(err)
        f_start, f_end = timesheet.timesheet_date_range(df)
        if (f_start.date(), f_end.date()) != (start.date(), end.date()):
            raise ValueError(f"File covers {_fmt(f_start)}→{_fmt(f_end)}, "
                             f"not the period {_fmt(start)}→{_fmt(end)}.")

        active = outlook.get_active_email()
        if active and active.lower().strip() != self.email.lower().strip():
            raise ValueError(f"Email {self.email} does not match Outlook account ({active}).")

        info = outlook.lookup_user(self.email)
        try:
            overlaps = n4w.find_overlaps(start, end, n4w.find_existing_submissions(info['email']))
        except Exception as e:   # heredado: si falla la verificación, se permite continuar
            self.cb.log(f"  ⚠ Could not check for duplicates: {e}")
            overlaps = []
        if overlaps:
            detail = "\n".join(f"• {o['start']} → {o['end']} ({o['filename']})" for o in overlaps)
            raise ValueError(f"Weeks already submitted:\n{detail}")

        rows = n4w.build_n4w_rows(df, info['email'], info['name'],
                                  n4w.load_timesheet_codes(self.task_details_path))
        name = n4w.n4w_filename(info['email'], start, end)
        local = n4w.write_n4w_excel(rows, self._path(name))

        self._approve("Submit to N4W Facility?",
                      f"{len(rows)} rows → OneDrive/{config.N4W_ONEDRIVE_FOLDER}/{name}")
        dst = n4w.put_file_in_onedrive(local, rf"{config.N4W_ONEDRIVE_FOLDER}\{name}",
                                       account_hint=config.ONEDRIVE_ACCOUNT_HINT, overwrite=True)
        self.cb.log(f"✓ Submitted: {dst}")
        return dst
