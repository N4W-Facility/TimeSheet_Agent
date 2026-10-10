# ============================================================
# RECORDATORIOS — qué debe decir Tributary en el escritorio (sin GUI, sin pandas)
#   month_end : hoy es el último día hábil del mes y Workday no está completo
#   prev_month: primeros días hábiles del mes y el mes anterior sigue sin Workday
#   update    : hay una versión nueva publicada (la revisa el acompañante al iniciar y
#               cada 6 h; cualquier día de 8 a 20). Solo se instala si el usuario acepta:
#               run_update() corre el mismo update.ps1 del lanzador.
# "Completo" = todos los días hábiles del mes (lun–vie sin festivos del país base)
# están dentro de algún paso 'workday' del historial (mes entero o semanas).
# Cada aviso sale una vez por día; ✕ lo calla hasta mañana, "Más tarde" una hora.
# ============================================================
import os
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Set

PREV_MONTH_DAYS = 3          # días hábiles del mes en que se recuerda cerrar el anterior
FIRST_HOUR, LAST_HOUR = 9, 18   # horario en que Tributary puede aparecer
UPDATE_FIRST_HOUR, UPDATE_LAST_HOUR = 8, 20   # el aviso de versión nueva, cualquier día
UPDATE_EVERY = timedelta(hours=6)
SNOOZE = timedelta(hours=1)
RELEASES_URL = "https://github.com/N4W-Facility/TimeSheet_Agent/releases/latest"   # igual que update.ps1


@dataclass
class Reminder:
    key: str                 # único por ocasión ("month_end:2026-10")
    msg: str                 # clave de agent/i18n.py
    kw: Dict[str, object] = field(default_factory=dict)


# ── Calendario ───────────────────────────────────────────────

def holidays_of(country: str, year: int) -> Set[date]:
    if not country:
        return set()
    try:
        import holidays
        return set(holidays.country_holidays(country, years=[year]))
    except Exception:                              # sin librería o país no soportado
        return set()


def business_days(year: int, month: int, country: str = "") -> List[date]:
    off = holidays_of(country, year)
    d, out = date(year, month, 1), []
    while d.month == month:
        if d.weekday() < 5 and d not in off:
            out.append(d)
        d += timedelta(days=1)
    return out


def _prev_month(d: date) -> date:
    return d.replace(day=1) - timedelta(days=1)


# ── Historial (lectura directa: el acompañante no carga pandas) ──

def workday_days(db_path: str) -> Set[date]:
    """Días cubiertos por algún paso 'workday' del historial."""
    if not os.path.exists(db_path):
        return set()
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT period_start, period_end FROM events WHERE step = 'workday'").fetchall()
    except sqlite3.Error:
        rows = []
    finally:
        conn.close()
    days = set()
    for start, end in rows:
        try:
            d, last = date.fromisoformat(start[:10]), date.fromisoformat(end[:10])
        except (TypeError, ValueError):
            continue
        while d <= last:
            days.add(d)
            d += timedelta(days=1)
    return days


def month_filled(year: int, month: int, filled: Set[date], country: str = "") -> bool:
    return all(d in filled for d in business_days(year, month, country))


def due(today: date, filled: Set[date], country: str = "") -> List[Reminder]:
    """Recordatorios de horas que tocan hoy (el de versión nueva va aparte)."""
    out = []
    days = business_days(today.year, today.month, country)
    if days and today == days[-1] and not month_filled(today.year, today.month, filled, country):
        out.append(Reminder(f"month_end:{today:%Y-%m}", "remind_month_end", {"month": today}))
    if today in days[:PREV_MONTH_DAYS]:
        prev = _prev_month(today)
        if not month_filled(prev.year, prev.month, filled, country):
            out.append(Reminder(f"prev_month:{prev:%Y-%m}", "remind_prev_month", {"month": prev}))
    return out


def in_hours(now: datetime) -> bool:
    return now.weekday() < 5 and FIRST_HOUR <= now.hour < LAST_HOUR


def in_update_hours(now: datetime) -> bool:
    return UPDATE_FIRST_HOUR <= now.hour < UPDATE_LAST_HOUR


# ── Ya mostrado / callado (tabla profile de history.db) ───────

class Seen:
    """profile['reminder:<clave>'] = fecha en que el usuario lo atendió o lo calló.
    get/put: otros datos del perfil (dónde dejó el usuario a Tributary)."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._snoozed: Dict[str, datetime] = {}

    def _run(self, sql, args=()):
        conn = sqlite3.connect(self.db_path)
        try:
            with conn:
                conn.execute("CREATE TABLE IF NOT EXISTS profile (key TEXT PRIMARY KEY, value TEXT, updated TEXT)")
                return conn.execute(sql, args).fetchone()
        finally:
            conn.close()

    def get(self, key: str) -> str:
        try:
            row = self._run("SELECT value FROM profile WHERE key = ?", (key,))
        except sqlite3.Error:
            return ""
        return row[0] if row and row[0] else ""

    def put(self, key: str, value: str):
        try:
            self._run("INSERT OR REPLACE INTO profile VALUES (?, ?, ?)",
                      (key, value, datetime.now().isoformat(timespec='seconds')))
        except sqlite3.Error:                     # base bloqueada un instante: no es grave
            pass

    def done_today(self, key: str, today: date) -> bool:
        return self.get(f"reminder:{key}") == today.isoformat()

    def mark(self, key: str, today: date):
        self.put(f"reminder:{key}", today.isoformat())

    def snooze(self, key: str, now: datetime, delta: timedelta = SNOOZE):
        self._snoozed[key] = now + delta

    def pending(self, reminders: List[Reminder], now: datetime) -> Optional[Reminder]:
        for r in reminders:
            if self._snoozed.get(r.key, now) > now or self.done_today(r.key, now.date()):
                continue
            return r
        return None


# ── Versión nueva ────────────────────────────────────────────

def latest_version() -> str:
    """Tag del último release ('' sin red). curl.exe como update.ps1: el proxy/EDR corta .NET/Python."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)       # pythonw: sin ventana de consola
    try:
        out = subprocess.run(["curl.exe" if sys.platform == "win32" else "curl", "-s", "-o",
                              os.devnull, "-w", "%{redirect_url}", "-m", "8", RELEASES_URL],
                             capture_output=True, text=True, timeout=15, creationflags=flags).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.rsplit("/releases/tag/", 1)[1].strip() if "/releases/tag/" in out else ""


def update_reminder(installed: str, latest: str) -> Optional[Reminder]:
    norm = lambda v: (v or "").strip().lstrip("vV")
    if not latest or not installed or installed == "local" or norm(installed) == norm(latest):
        return None
    return Reminder(f"update:{latest}", "remind_update", {"version": latest})


def release_page(tag: str) -> str:
    """Página del release (novedades) en GitHub."""
    return f"{RELEASES_URL.rsplit('/', 1)[0]}/tag/{tag}"


def installed_version(tsa_home: str) -> str:
    try:
        with open(os.path.join(tsa_home, "version.txt"), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""                                  # desde el repo: sin versión instalada


def env_changed(tsa_home: str) -> bool:
    """¿La versión nueva cambió environment.yml? Entonces el lanzador debe recrear el ambiente
    (mismo hash SHA256 que guarda TimeSheet_Agent.bat en .environment.sha256)."""
    import hashlib
    yml = os.path.join(tsa_home, "app", "environment.yml")
    stamp = os.path.join(tsa_home, "mamba", "envs", "timesheet-agent", ".environment.sha256")
    try:
        with open(yml, "rb") as f:
            new = hashlib.sha256(f.read()).hexdigest().upper()
        with open(stamp, encoding="utf-8", errors="ignore") as f:
            old = f.read().strip().upper()
    except OSError:
        return True
    return new != old


def run_update(tsa_home: str):
    """Corre update.ps1 sin ventana. → ('updated' | 'current' | 'busy' | 'failed', salida)."""
    script = os.path.join(tsa_home, "app", "update.ps1")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                              "-TsaHome", tsa_home], capture_output=True, text=True, timeout=900,
                             creationflags=flags, cwd=tsa_home)
        text = (out.stdout or "") + (out.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return "failed", str(e)
    return update_status(text), text.strip()


def update_status(output: str) -> str:
    """Estado según los mensajes de update.ps1."""
    if "Updated to" in output:
        return "updated"
    if "Up to date" in output or "No release published" in output:
        return "current"
    if "is open" in output:                        # app\ en uso: no se pudo cambiar la carpeta
        return "busy"
    return "failed"
