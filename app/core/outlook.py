# ============================================================
# OUTLOOK (COM) — calendario, categorías e identidad del usuario
# Solo Windows: los imports de win32com van dentro de las funciones
# para que el resto del paquete se pueda importar/testear en Linux.
# ============================================================
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

from config import EXPECTED_DAILY_HOURS
from core.utils import remove_timezone

log = logging.getLogger(__name__)

# Combinaciones de buffer (días) que se prueban hasta que Outlook devuelva datos
BUFFER_CONFIGS = [13, 2, 3, 5, 7, 11, 17, 19, 23, 29, 31]


def get_calendar(start_date: str, end_date: str, buffer_start=25, buffer_end=25) -> pd.DataFrame:
    """
    Reuniones del calendario entre start_date y end_date ('YYYY-MM-DD').
    Returns: DataFrame [Date, Category, Hours]
    """
    import win32com.client
    from tzlocal import get_localzone

    outlook_app = win32com.client.Dispatch("Outlook.Application")
    namespace = outlook_app.GetNamespace("MAPI")
    calendar = namespace.GetDefaultFolder(9)

    local_tz = get_localzone()
    start = datetime.strptime(start_date, '%Y-%m-%d').replace(tzinfo=local_tz)
    end = datetime.strptime(end_date, '%Y-%m-%d').replace(tzinfo=local_tz)

    items = calendar.Items
    items.IncludeRecurrences = True
    items.Sort("[Start]")

    start_str = (start - timedelta(days=buffer_start)).strftime('%m/%d/%Y %H:%M')
    end_str = (end + timedelta(days=buffer_end)).strftime('%m/%d/%Y %H:%M')
    restricted = items.Restrict(f"[Start] >= '{start_str}' AND [End] <= '{end_str}'")

    meetings = []
    for item in restricted:
        try:
            m_start, m_end = item.Start, item.End
            category = item.Categories if item.Categories else "Sin Category"
            if item.AllDayEvent:
                meetings += all_day_entries(remove_timezone(m_start), remove_timezone(m_end), category,
                                            remove_timezone(start), remove_timezone(end))
            elif remove_timezone(start) <= remove_timezone(m_start) <= remove_timezone(end):
                meetings.append({
                    'Date': m_start.date(),
                    'Category': category,
                    'Hours': (m_end - m_start).total_seconds() / 3600,
                })
        except AttributeError:
            continue
    return pd.DataFrame(meetings)


def all_day_entries(m_start: datetime, m_end: datetime, category: str,
                    start: datetime, end_exclusive: datetime) -> List[dict]:
    """
    Evento de día completo (p. ej. vacaciones de varios días): 8 h por cada día
    lunes–viernes que cubre dentro del rango, no las 24 h × días que dura.
    """
    out = []
    for d in pd.date_range(m_start.date(), m_end.date() - timedelta(days=1), freq='D'):
        if d.weekday() < 5 and start <= d < end_exclusive:
            out.append({'Date': d.date(), 'Category': category, 'Hours': EXPECTED_DAILY_HOURS})
    return out


def read_meetings(start: datetime, end_exclusive: datetime) -> pd.DataFrame:
    """
    Lee el calendario probando varias combinaciones de buffer
    (Outlook a veces devuelve vacío con un Restrict dado).
    """
    s, e = start.strftime('%Y-%m-%d'), end_exclusive.strftime('%Y-%m-%d')
    for b1 in BUFFER_CONFIGS:
        for b2 in BUFFER_CONFIGS:
            results = get_calendar(s, e, b1, b2)
            if len(results.columns) != 0:
                return results
    return pd.DataFrame(columns=['Date', 'Category', 'Hours'])


def _restricted_items(start: datetime, end_exclusive: datetime):
    """Ocurrencias del calendario que empiezan en [start, end_exclusive) (incluye recurrentes)."""
    import win32com.client

    calendar = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI").GetDefaultFolder(9)
    items = calendar.Items
    items.IncludeRecurrences = True
    items.Sort("[Start]")
    restricted = items.Restrict(f"[Start] >= '{start:%m/%d/%Y %H:%M}' AND [Start] < '{end_exclusive:%m/%d/%Y %H:%M}'")
    for item in restricted:
        try:
            m_start = remove_timezone(item.Start)
            if start <= m_start < end_exclusive:
                yield item, m_start
        except AttributeError:
            continue


def calendar_entries(start: datetime, end_exclusive: datetime) -> List[dict]:
    """Reuniones con asunto y categorías: [{'subject', 'start', 'hours', 'categories'}]."""
    out = []
    for item, m_start in _restricted_items(start, end_exclusive):
        try:
            out.append({'subject': str(item.Subject or "").strip(), 'start': m_start,
                        'hours': (item.End - item.Start).total_seconds() / 3600,
                        'categories': str(item.Categories or "").strip()})
        except AttributeError:
            continue
    return out


def set_category(subject: str, start: datetime, category: str) -> bool:
    """
    Asigna la categoría a UNA reunión sin categoría (asunto + inicio exactos).
    En una recurrente se guarda solo esa ocurrencia (excepción), nunca la serie.
    """
    for item, m_start in _restricted_items(start - timedelta(minutes=1), start + timedelta(minutes=1)):
        if m_start == start and str(item.Subject or "").strip() == subject and not item.Categories:
            item.Categories = category
            item.Save()
            log.info(f"Category '{category}' → {subject} {start}")
            return True
    return False


def build_timesheet(meetings: pd.DataFrame, start: datetime, end: datetime,
                    db: pd.DataFrame) -> tuple:
    """
    Convierte reuniones en la tabla de horas por código y día.

    Args:
        meetings: salida de read_meetings
        start, end: rango inclusivo
        db: catálogo de códigos (database.catalog)

    Returns:
        (timesheet, unmapped)
        timesheet: DataFrame index=Code, columnas Task Name, Grant ID y fechas 'YYYY-MM-DD HH:MM:SS'
        unmapped: dict {categoría_outlook: horas} de categorías sin código conocido (se descartan)
    """
    end_exclusive = end + timedelta(days=1)

    tmp = meetings.groupby(by=['Date', 'Category'], as_index=False)['Hours'].sum()
    tmp['Hours'] = tmp['Hours'].apply(lambda x: round(x * 4) / 4)   # precisión 0.25 h
    tmp = tmp.pivot(index=['Category'], columns='Date', values='Hours').fillna(0)

    report = pd.DataFrame(columns=pd.date_range(start, end_exclusive, freq='D'))
    tmp.columns = pd.to_datetime(tmp.columns, errors='coerce')
    report.columns = pd.to_datetime(report.columns, errors='coerce')
    report = pd.concat([report, tmp], axis=0).fillna(0)
    report.columns = report.columns.map(
        lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if isinstance(x, pd.Timestamp) else x
    )
    # La categoría de Outlook es "CODE | Descripción" → nos quedamos con CODE
    # y sumamos: varias categorías con el mismo código (otra descripción) son el mismo proyecto
    report.index = [str(t).split('|')[0].strip() for t in report.index.values]
    report = report.groupby(level=0, sort=False).sum()

    codes = db.dropna(subset=['Code']).fillna(0).replace('XXXXXX', 0).set_index('Code')

    unmapped_idx = [c for c in report.index if c not in codes.index]
    unmapped = report.loc[unmapped_idx].sum(axis=1)
    unmapped = {k: float(v) for k, v in unmapped.groupby(level=0).sum().items() if v > 0}

    value = pd.merge(codes, report, left_index=True, right_index=True)
    value = value.drop(columns=['Description', 'Category', 'Include'])
    value = value.drop(columns=value.columns[-1])   # día extra (end_exclusive)
    value.index.name = 'Code'
    return value, unmapped


def list_categories() -> List[str]:
    """Nombres de las categorías de Outlook del usuario."""
    import win32com.client

    categories = win32com.client.Dispatch("Outlook.Application").Session.Categories
    return [categories.Item(i).Name for i in range(1, categories.Count + 1)]


def add_category(name: str) -> bool:
    """Crea una categoría de Outlook. False si ya existía."""
    import win32com.client

    categories = win32com.client.Dispatch("Outlook.Application").Session.Categories
    existing = [categories.Item(i).Name for i in range(1, categories.Count + 1)]
    if name in existing:
        return False
    categories.Add(name, categories.Count % 25 + 1)
    log.info(f"Outlook category created: {name}")
    return True


def get_active_email() -> Optional[str]:
    """Correo de la primera cuenta configurada en Outlook."""
    import win32com.client
    try:
        accounts = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI").Accounts
        if accounts.Count > 0:
            return accounts.Item(1).SmtpAddress
    except Exception as e:
        log.warning(f"Could not detect Outlook email: {e}")
    return None


def lookup_user(email: str) -> Optional[Dict[str, str]]:
    """
    Nombre asociado a un correo: GAL (Exchange/365) → Contactos → display name.
    Returns: {'email', 'name', ...} o None
    """
    import win32com.client
    from win32com.client import constants

    result = {"email": email, "name": None}
    try:
        session = win32com.client.Dispatch("Outlook.Application").Session

        recipient = session.CreateRecipient(email)
        recipient.Resolve()
        if recipient.Resolved:
            ae = recipient.AddressEntry
            result["name"] = ae.Name
            try:
                ex_user = ae.GetExchangeUser()
            except Exception:
                ex_user = None
            if ex_user:
                result.update({
                    "email": ex_user.PrimarySmtpAddress or email,
                    "name": ex_user.Name or ae.Name or None,
                })
                for attr, key in (("JobTitle", "job_title"), ("CompanyName", "company")):
                    try:
                        if getattr(ex_user, attr):
                            result[key] = getattr(ex_user, attr)
                    except Exception:
                        pass
                return result
            if result["name"]:
                return result

        try:
            items = session.GetDefaultFolder(constants.olFolderContacts).Items
            for field in ("Email1Address", "Email2Address", "Email3Address"):
                found = items.Find(f"[{field}] = '{email}'")
                if found:
                    result["name"] = getattr(found, "FullName", None) or getattr(found, "CompanyName", None)
                    normalized = getattr(found, field, None)
                    if normalized:
                        result["email"] = normalized
                    return result
        except Exception:
            pass

        if not recipient.Resolved:
            recipient = session.CreateRecipient(email)
            recipient.Resolve()
        if recipient and recipient.Resolved:
            result["name"] = recipient.Name or result["name"]

        return result if (result.get("name") or result.get("email")) else None
    except Exception as e:
        raise RuntimeError(f"Unable to access Outlook: {e}")
