# ============================================================
# OUTLOOK (COM) — calendario, categorías e identidad del usuario
# Solo Windows: los imports de win32com van dentro de las funciones
# para que el resto del paquete se pueda importar/testear en Linux.
# ============================================================
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd

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
            if remove_timezone(start) <= remove_timezone(m_start) <= remove_timezone(end):
                meetings.append({
                    'Date': m_start.date(),
                    'Category': item.Categories if item.Categories else "Sin Category",
                    'Hours': (m_end - m_start).total_seconds() / 3600,
                })
        except AttributeError:
            continue
    return pd.DataFrame(meetings)


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


def build_timesheet(meetings: pd.DataFrame, start: datetime, end: datetime,
                    db: pd.DataFrame) -> tuple:
    """
    Convierte reuniones en la tabla de horas por código y día.

    Args:
        meetings: salida de read_meetings
        start, end: rango inclusivo
        db: hoja de proyectos (read_database)

    Returns:
        (timesheet, unmapped)
        timesheet: DataFrame index=Code, columnas Task Name, Grant ID y fechas 'YYYY-MM-DD HH:MM:SS'
        unmapped: dict {categoría_outlook: horas} de categorías sin código en la BD (se descartan)
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
    report.index = [str(t).split('|')[0].strip() for t in report.index.values]

    codes = db.dropna(subset=['Code']).fillna(0).replace('XXXXXX', 0).set_index('Code')

    unmapped_idx = [c for c in report.index if c not in codes.index]
    unmapped = report.loc[unmapped_idx].sum(axis=1)
    unmapped = {k: float(v) for k, v in unmapped.groupby(level=0).sum().items() if v > 0}

    value = pd.merge(codes, report, left_index=True, right_index=True)
    value = value.drop(columns=['Description', 'Category', 'Include'])
    value = value.drop(columns=value.columns[-1])   # día extra (end_exclusive)
    value.index.name = 'Code'
    return value, unmapped


def sync_categories(db: pd.DataFrame, on_progress=None):
    """Crea/elimina categorías de Outlook según la columna Include de la BD."""
    import pythoncom
    import win32com.client

    df = db.dropna(subset=['Code']).fillna(0)
    for column in ('Category', 'Include'):
        if column not in df.columns:
            raise ValueError(f"La BD debe tener la columna '{column}'.")

    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        categories = outlook.Session.Categories
        existing = [categories.Item(i).Name for i in range(1, categories.Count + 1)]

        total = len(df)
        for n, (i, row) in enumerate(df.iterrows(), 1):
            name, include = row['Category'], row['Include']
            color_index = row.get('ColorIndex', i % 25 + 1)
            if include == 1 and name not in existing:
                categories.Add(name, color_index)
            elif include == 0 and name in existing:
                categories.Remove(name)

            time.sleep(0.25)
            if i % 10 == 0:
                pythoncom.PumpWaitingMessages()   # evita desconexiones COM
            if on_progress:
                on_progress(n, total)
    finally:
        pythoncom.CoUninitialize()


def get_active_email() -> Optional[str]:
    """Correo de la primera cuenta configurada en Outlook."""
    import win32com.client
    try:
        accounts = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI").Accounts
        if accounts.Count > 0:
            return accounts.Item(1).SmtpAddress
    except Exception as e:
        log.warning(f"No se pudo detectar el correo de Outlook: {e}")
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
        raise RuntimeError(f"No se pudo acceder a Outlook: {e}")
