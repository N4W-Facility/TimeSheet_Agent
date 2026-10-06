# ============================================================
# PIPELINE GUIADO
# Pasos fijos en Python. Toda interacción (logs, decisiones,
# aprobaciones) sale por callbacks → la misma lógica sirve
# para la CLI, la GUI y el agente (Ollama).
# ============================================================
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional

import pandas as pd

import config
from core import database, n4w, outlook, prorate, timesheet


@dataclass
class Decision:
    """Pregunta que el pipeline no puede resolver solo."""
    kind: str                 # 'prorate_targets', ... (fase 2: 'workday_option', 'unmapped_category')
    question: str
    options: List[str]
    multi: bool = False       # True → se esperan varias opciones
    context: dict = field(default_factory=dict)


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


class Pipeline:
    """
    Contexto de un periodo. Cada método público es un paso independiente
    (el agente los usará como herramientas).
    """

    def __init__(self, db_path: str, start: datetime, end: datetime,
                 email: Optional[str] = None, callbacks: Optional[Callbacks] = None):
        self.db_path = os.path.abspath(db_path)
        self.workdir = os.path.dirname(self.db_path)
        self.start, self.end = start, end
        self.email = email
        self.cb = callbacks or Callbacks()

        self.task_details_path = self._path(config.N4W_TASK_DETAILS_NAME)
        self.timesheet_path = self._path(config.TIMESHEET_NAME)
        self.prorate_path = self._path(config.PRORATE_NAME)

        handler = _CallbackHandler(self.cb.log)
        core_log = logging.getLogger("core")
        core_log.handlers = [handler]
        core_log.setLevel(logging.INFO)
        core_log.propagate = False

    def _path(self, name: str) -> str:
        return os.path.join(self.workdir, name)

    def _approve(self, title: str, detail: str):
        if not self.cb.approve(title, detail):
            raise Cancelled(f"Cancelado por el usuario: {title}")

    # ── Paso 1: base de datos ────────────────────────────────
    def update_database(self) -> list:
        self.cb.log("Descargando códigos N4W desde Box...")
        database.download_box_file(config.BOX_URL, self.task_details_path)
        removed = database.update_database(self.db_path, self.task_details_path)
        for p in removed:
            self.cb.log(f"  − {p['code']} {p['description']} ({p['reason']})")
        return removed

    def sync_categories(self):
        """Crea/elimina las categorías de Outlook según la BD (Include)."""
        self.cb.log("Sincronizando categorías de Outlook...")
        outlook.sync_categories(database.read_database(self.db_path))
        self.cb.log("✓ Categorías sincronizadas")

    # ── Paso 2: Outlook → timesheet ──────────────────────────
    def build_timesheet(self) -> dict:
        """Genera 01-Report.xlsx y 02-Timesheet.csv. Devuelve hallazgos para revisar."""
        if self.start > self.end:
            raise ValueError("La fecha de inicio es posterior a la de fin.")
        self.cb.log(f"Leyendo Outlook {self.start:%Y-%m-%d} → {self.end:%Y-%m-%d}...")
        meetings = outlook.read_meetings(self.start, self.end + pd.Timedelta(days=1))
        if meetings.empty:
            raise ValueError("Outlook no devolvió reuniones en el periodo.")

        db = database.read_database(self.db_path)
        ts, unmapped = outlook.build_timesheet(meetings, self.start, self.end, db)

        meetings.to_excel(self._path(config.REPORT_NAME))
        ts.to_csv(self.timesheet_path, index_label='Code')
        self.cb.log(f"✓ {config.TIMESHEET_NAME}: {len(ts)} códigos")

        df = ts.reset_index()
        findings = {
            'unmapped': unmapped,
            'irregular_days': timesheet.find_irregular_days(df),
            'summary': timesheet.summarize(df),
        }
        for cat, h in unmapped.items():
            self.cb.log(f"  ⚠ Categoría sin código (descartada): '{cat}' — {h:g} h")
        for d in findings['irregular_days']:
            self.cb.log(f"  ⚠ {d['date']}: {d['hours']:g} h ({d['issue']})")
        return findings

    # ── Paso 3 (opcional): prorrateo ─────────────────────────
    def prorate(self) -> str:
        """Reparte horas virtuales → 03-Timesheet_Prorate.csv. Devuelve la ruta."""
        ts = pd.read_csv(self.timesheet_path)
        candidates = prorate.real_projects(ts, self.task_details_path)
        selected = self.cb.decide(Decision(
            kind='prorate_targets',
            question="¿Qué proyectos reciben las horas prorrateadas?",
            options=candidates, multi=True,
        ))
        if selected is None:
            raise Cancelled("Prorrateo cancelado")
        selections = {c: c in selected for c in candidates}

        result = prorate.redistribute(ts, self.task_details_path, selections, self.db_path)
        before = timesheet.summarize(ts)['Total'].rename('Original')
        after = timesheet.summarize(result)['Total'].rename('Prorrateo')
        comparison = pd.concat([before, after], axis=1).fillna(0)
        self._approve("Comparación del prorrateo", comparison.to_string())

        result.to_csv(self.prorate_path, index=False)
        self.cb.log(f"✓ {config.PRORATE_NAME}")
        return self.prorate_path

    # ── Paso 4: Workday ──────────────────────────────────────
    def fill_workday(self, csv_path: Optional[str] = None, confirm_each_week: bool = True):
        """
        Requiere Chrome con CDP, sesión iniciada y la tabla
        'Introducción de horas por tipo' de la PRIMERA semana abierta.
        """
        from core.workday.automation import WorkdayAutomation
        from core.workday.browser_launcher import is_cdp_running, launch_chrome
        from core.workday.csv_reader import parse_csv

        csv_path = csv_path or self.timesheet_path
        weeks = parse_csv(csv_path)
        self.cb.log(f"{len(weeks)} semanas | {sum(len(p) for p in weeks.values())} entradas")

        if not is_cdp_running() and not launch_chrome(log_callback=self.cb.log):
            raise RuntimeError("No se pudo abrir Chrome con depuración remota.")
        self._approve(
            "Workday listo",
            "Inicia sesión y abre 'Introducción de horas por tipo' en la semana "
            f"del {next(iter(weeks))}. ¿Listo para empezar?")

        confirm = (lambda msg: self.cb.approve("Guardar semana", msg)) if confirm_each_week else (lambda msg: True)
        auto = WorkdayAutomation(log_callback=self.cb.log, confirm_callback=confirm)
        try:
            auto.connect()
            auto.detect_lang()
            auto.run(weeks)
        finally:
            auto.close()

    # ── Paso 5: N4W Facility ─────────────────────────────────
    def submit_n4w(self, csv_path: Optional[str] = None) -> str:
        """Valida, genera el Excel N4W y lo copia a OneDrive. Devuelve la ruta destino."""
        if not self.email:
            raise ValueError("Se requiere el correo del usuario para N4W.")
        csv_path = csv_path or self.timesheet_path
        df = pd.read_csv(csv_path)

        ok, err = timesheet.validate_complete_weeks(self.start, self.end)
        if not ok:
            raise ValueError(err)
        f_start, f_end = timesheet.timesheet_date_range(df)
        if (f_start.date(), f_end.date()) != (self.start.date(), self.end.date()):
            raise ValueError(f"El archivo cubre {f_start:%Y-%m-%d}→{f_end:%Y-%m-%d}, "
                             f"no el periodo {self.start:%Y-%m-%d}→{self.end:%Y-%m-%d}.")

        active = outlook.get_active_email()
        if active and active.lower().strip() != self.email.lower().strip():
            raise ValueError(f"El correo {self.email} no coincide con Outlook ({active}).")

        info = outlook.lookup_user(self.email)
        try:
            overlaps = n4w.find_overlaps(self.start, self.end, n4w.find_existing_submissions(info['email']))
        except Exception as e:   # heredado: si falla la verificación, se permite continuar
            self.cb.log(f"  ⚠ No se pudo verificar duplicados: {e}")
            overlaps = []
        if overlaps:
            detail = "\n".join(f"• {o['start']} → {o['end']} ({o['filename']})" for o in overlaps)
            raise ValueError(f"Semanas ya entregadas:\n{detail}")

        rows = n4w.build_n4w_rows(df, info['email'], info['name'],
                                  n4w.load_timesheet_codes(self.task_details_path))
        name = n4w.n4w_filename(info['email'], self.start, self.end)
        local = n4w.write_n4w_excel(rows, self._path(name))

        self._approve("Enviar a N4W Facility",
                      f"{len(rows)} filas → OneDrive/{config.N4W_ONEDRIVE_FOLDER}/{name}")
        dst = n4w.put_file_in_onedrive(local, rf"{config.N4W_ONEDRIVE_FOLDER}\{name}",
                                       account_hint=config.ONEDRIVE_ACCOUNT_HINT, overwrite=True)
        self.cb.log(f"✓ Entregado: {dst}")
        return dst
