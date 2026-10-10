# ============================================================
# HISTORIAL LOCAL (SQLite) — memoria del agente mes a mes
#   hours   : horas por día y código; source = 'outlook' | 'prorated'
#   targets : dedicación objetivo por código (% del mes y/o horas/mes)
#   events  : pasos realizados (read, prorate, workday, n4w)
#   projects: "mis proyectos" (códigos en los que trabaja el usuario; removed = quitado)
#   dismissed: propuestas de revisión rechazadas (no se repiten por un tiempo)
#   profile : datos del usuario (country = país base, confirmado por él)
# Lo "cargado" de un mes es la versión prorrateada si existe; si no, la de Outlook.
# ============================================================
import os
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from core.analysis import LONG_COLUMNS, to_long
from core.utils import get_date_columns

SCHEMA = """
CREATE TABLE IF NOT EXISTS hours (
    day TEXT NOT NULL, code TEXT NOT NULL, source TEXT NOT NULL,
    task_name TEXT, hours REAL NOT NULL,
    PRIMARY KEY (day, code, source));
CREATE TABLE IF NOT EXISTS targets (
    code TEXT PRIMARY KEY, pct REAL, hours REAL, updated TEXT);
CREATE TABLE IF NOT EXISTS events (
    period_start TEXT, period_end TEXT, step TEXT, at TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS projects (
    code TEXT PRIMARY KEY, added TEXT, removed TEXT);
CREATE TABLE IF NOT EXISTS dismissed (
    code TEXT, reason TEXT, at TEXT, PRIMARY KEY (code, reason));
CREATE TABLE IF NOT EXISTS profile (
    key TEXT PRIMARY KEY, value TEXT, updated TEXT);
"""

# Por cada mes: filas prorrateadas si existen, si no las de Outlook
CHARGED_SQL = """
SELECT day, code, task_name, hours FROM hours h
WHERE day BETWEEN ? AND ?
  AND (source = 'prorated' OR (source = 'outlook' AND NOT EXISTS (
       SELECT 1 FROM hours p WHERE p.source = 'prorated'
       AND substr(p.day, 1, 7) = substr(h.day, 1, 7))))
ORDER BY day, code
"""


def _d(x) -> str:
    return x.strftime('%Y-%m-%d') if isinstance(x, datetime) else str(x)[:10]


class History:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self._run(lambda c: c.executescript(SCHEMA))

    def _run(self, fn):
        conn = sqlite3.connect(self.path)
        try:
            with conn:
                return fn(conn)
        finally:
            conn.close()

    # ── Horas ────────────────────────────────────────────────
    def save(self, timesheet: pd.DataFrame, source: str, start=None, end=None):
        """Reemplaza las horas de `source` en el rango (por defecto, el de las columnas)."""
        long = to_long(timesheet)
        if start is None:
            days = sorted(str(c)[:10] for c in get_date_columns(timesheet))
            if not days:
                return
            start, end = days[0], days[-1]
        rows = [(r['day'], r['code'], source, r['task_name'], float(r['hours']))
                for r in long.to_dict('records')]

        def tx(c):
            c.execute("DELETE FROM hours WHERE source = ? AND day BETWEEN ? AND ?",
                      (source, _d(start), _d(end)))
            c.executemany("INSERT INTO hours VALUES (?, ?, ?, ?, ?)", rows)
        self._run(tx)

    def clear(self, start, end, source: str):
        self._run(lambda c: c.execute("DELETE FROM hours WHERE source = ? AND day BETWEEN ? AND ?",
                                      (source, _d(start), _d(end))))

    def hours(self, start, end) -> pd.DataFrame:
        """Horas cargadas en [start, end] (formato largo)."""
        return self._run(lambda c: pd.read_sql_query(CHARGED_SQL, c, params=(_d(start), _d(end))))

    def all_hours(self, before=None) -> pd.DataFrame:
        """Todo el historial (opcional: solo días anteriores a `before`)."""
        end = (pd.Timestamp(_d(before)) - pd.Timedelta(days=1)).strftime('%Y-%m-%d') if before else '9999-12-31'
        df = self.hours('0000-01-01', end)
        return df if not df.empty else pd.DataFrame(columns=LONG_COLUMNS)

    def months(self) -> list:
        return self._run(lambda c: [r[0] for r in c.execute(
            "SELECT DISTINCT substr(day, 1, 7) FROM hours ORDER BY 1")])

    def was_read(self, start, end) -> bool:
        """True si el periodo completo ya se leyó de Outlook (paso read o carga de historial)."""
        return self._run(lambda c: c.execute(
            "SELECT 1 FROM events WHERE step IN ('read', 'history') "
            "AND period_start <= ? AND period_end >= ? LIMIT 1",
            (_d(start), _d(end))).fetchone() is not None)

    # ── Objetivos ────────────────────────────────────────────
    def set_target(self, code: str, pct: Optional[float] = None, hours: Optional[float] = None):
        now = datetime.now().isoformat(timespec='seconds')
        self._run(lambda c: c.execute(
            "INSERT INTO targets VALUES (?, ?, ?, ?) ON CONFLICT(code) DO UPDATE SET "
            "pct = COALESCE(excluded.pct, pct), hours = COALESCE(excluded.hours, hours), "
            "updated = excluded.updated", (code, pct, hours, now)))

    def targets(self) -> Dict[str, dict]:
        rows = self._run(lambda c: list(c.execute("SELECT code, pct, hours FROM targets")))
        return {code: {'pct': pct, 'hours': hrs} for code, pct, hrs in rows}

    # ── Perfil del usuario ───────────────────────────────────
    def profile(self, key: str) -> str:
        row = self._run(lambda c: c.execute("SELECT value FROM profile WHERE key = ?", (key,)).fetchone())
        return row[0] if row and row[0] else ""

    def set_profile(self, key: str, value: str):
        self._run(lambda c: c.execute("INSERT OR REPLACE INTO profile VALUES (?, ?, ?)",
                                      (key, value, datetime.now().isoformat(timespec='seconds'))))

    # ── Mis proyectos ────────────────────────────────────────
    def my_projects(self) -> List[str]:
        return self._run(lambda c: [r[0] for r in c.execute(
            "SELECT code FROM projects WHERE removed IS NULL ORDER BY code")])

    def projects_initialized(self) -> bool:
        """True si el usuario ya armó su lista alguna vez (aunque luego quitara todo)."""
        return self._run(lambda c: c.execute("SELECT 1 FROM projects LIMIT 1").fetchone() is not None)

    def project_added(self, code: str) -> Optional[str]:
        row = self._run(lambda c: c.execute(
            "SELECT added FROM projects WHERE code = ? AND removed IS NULL", (code,)).fetchone())
        return row[0] if row else None

    def add_projects(self, codes: List[str]):
        now = datetime.now().isoformat(timespec='seconds')
        self._run(lambda c: c.executemany(
            "INSERT INTO projects VALUES (?, ?, NULL) ON CONFLICT(code) DO UPDATE SET "
            "added = CASE WHEN removed IS NULL THEN added ELSE excluded.added END, removed = NULL",
            [(code, now) for code in codes]))

    def remove_projects(self, codes: List[str]):
        now = datetime.now().isoformat(timespec='seconds')
        self._run(lambda c: c.executemany(
            "UPDATE projects SET removed = ? WHERE code = ?", [(now, code) for code in codes]))

    def dismiss(self, code: str, reason: str):
        now = datetime.now().isoformat(timespec='seconds')
        self._run(lambda c: c.execute(
            "INSERT OR REPLACE INTO dismissed VALUES (?, ?, ?)", (code, reason, now)))

    def dismissed(self, since: str) -> Set[Tuple[str, str]]:
        """(código, motivo) rechazados desde la fecha ISO `since`."""
        return self._run(lambda c: {(code, reason) for code, reason in c.execute(
            "SELECT code, reason FROM dismissed WHERE at >= ?", (since,))})

    # ── Eventos ──────────────────────────────────────────────
    def log_event(self, start, end, step: str, detail: str = ""):
        now = datetime.now().isoformat(timespec='seconds')
        self._run(lambda c: c.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                                      (_d(start), _d(end), step, now, detail)))

    def last_read(self, start=None, end=None) -> Optional[dict]:
        """Último periodo leído con el paso 'read' (o la última lectura de start–end)
        y los pasos hechos después sobre ese periodo."""
        where, args = ("AND period_start = ? AND period_end = ? ", (_d(start), _d(end))) \
            if start is not None else ("", ())

        def q(c):
            row = c.execute("SELECT rowid, period_start, period_end, at FROM events "
                            "WHERE step = 'read' " + where + "ORDER BY rowid DESC LIMIT 1", args).fetchone()
            if not row:
                return None
            rowid, start, end, at = row
            steps = [r[0] for r in c.execute(
                "SELECT step FROM events WHERE rowid > ? AND period_start = ? AND period_end = ? "
                "ORDER BY rowid", (rowid, start, end))]
            return {'start': start, 'end': end, 'at': at, 'steps': steps}
        return self._run(q)

    def events(self, start, end) -> pd.DataFrame:
        return self._run(lambda c: pd.read_sql_query(
            "SELECT * FROM events WHERE period_start <= ? AND period_end >= ? ORDER BY at",
            c, params=(_d(end), _d(start))))
