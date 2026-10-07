# ============================================================
# BASE GLOBAL DE PROYECTOS (N4W_Task_Details.xlsx, de Box)
# Es la única fuente de nombres, Task Name, Grant ID, estado
# (activo / cerrado) y Prorate. "Mis proyectos" (los códigos en los
# que trabaja el usuario) viven en el historial (core/history.py).
# ============================================================
import logging
import re
from typing import List, Optional, Tuple

import pandas as pd
import requests

from config import INTERNAL_CODES, LEGACY_DB_SHEET
from core.utils import is_special_code

log = logging.getLogger(__name__)

CATALOG_COLUMNS = ['Code', 'Description', 'Task Name', 'Grant ID', 'Category', 'Include']
CODE_RE = re.compile(r"^[A-Z]{2}\d{3,5}[A-Z]{0,2}$")    # forma de un código (OF0104, FS3602A)


def download_box_file(url_box: str, output_path: str) -> str:
    """Descarga el archivo N4W_Task_Details.xlsx desde un enlace compartido de Box."""
    url_descarga = url_box.replace('/s/', '/shared/static/')
    response = requests.get(url_descarga, timeout=60)
    response.raise_for_status()
    with open(output_path, 'wb') as f:
        f.write(response.content)
    log.info(f"Box file downloaded: {output_path}")
    return output_path


def _is_empty(value) -> bool:
    if value is None or pd.isna(value):
        return True
    return isinstance(value, str) and len(value.strip()) == 0


def _text(value) -> str:
    return "" if _is_empty(value) else str(value).strip()


def category_name(code: str, description: str) -> str:
    """Categoría de Outlook: 'CODE | Descripción' (el código es lo que se lee)."""
    return f"{code} | {description}"


def find_category(code: str, names: List[str]) -> Optional[str]:
    """Categoría existente para el código, aunque su descripción sea otra ('OF0104 | texto viejo')."""
    want = str(code).strip().upper()
    return next((n for n in names if str(n).split('|')[0].strip().upper() == want), None)


def task_status(task_details_path: str) -> dict:
    """
    Estado global de todos los proyectos de N4W_Task_Details.xlsx:
    CÓDIGO (mayúsculas) → {'status': 'active'|'closed'|'not_opened', 'prorate': bool,
                           'description', 'task_name', 'grant_id', 'opened', 'closed'}
    """
    df = pd.read_excel(task_details_path)
    out = {}
    for _, r in df.iterrows():
        if _is_empty(r.get('Task_Name')):
            continue
        if _is_empty(r.get('Date_Opened')):
            status = 'not_opened'
        elif not _is_empty(r.get('Date_Closed')):
            status = 'closed'
        else:
            status = 'active'
        prorate = r.get('Prorate')
        opened, closed = r.get('Date_Opened'), r.get('Date_Closed')
        out[str(r['Task_Name']).strip().upper()] = {
            'status': status,
            'prorate': not _is_empty(prorate) and int(prorate) == 1,
            'description': _text(r.get('Task_Name_Description')),
            'task_name': _text(r.get('WD_TaskName')),
            'grant_id': _text(r.get('WD_GrantID')),
            'opened': None if _is_empty(opened) else pd.Timestamp(opened).strftime('%Y-%m-%d'),
            'closed': None if _is_empty(closed) else pd.Timestamp(closed).strftime('%Y-%m-%d'),
        }
    return out


def catalog(task_details_path: str) -> pd.DataFrame:
    """
    Todos los códigos conocidos (base global + internos XX) con las columnas que
    usan outlook.build_timesheet y el prorrateo: Code, Description, Task Name,
    Grant ID, Category, Include.
    """
    rows = [{'Code': code, 'Description': name, 'Task Name': name, 'Grant ID': '-'}
            for code, name in INTERNAL_CODES.items()]
    df = pd.read_excel(task_details_path)
    for _, r in df.iterrows():
        if _is_empty(r.get('Task_Name')):
            continue
        rows.append({'Code': str(r['Task_Name']).strip(),
                     'Description': _text(r.get('Task_Name_Description')),
                     'Task Name': _text(r.get('WD_TaskName')),
                     'Grant ID': _text(r.get('WD_GrantID'))})
    out = pd.DataFrame(rows).drop_duplicates(subset=['Code'])
    out['Category'] = [category_name(c, d) for c, d in zip(out['Code'], out['Description'])]
    out['Include'] = 1
    return out[CATALOG_COLUMNS].reset_index(drop=True)


def extract_codes(text: str, status: dict) -> Tuple[List[str], List[str]]:
    """
    Códigos escritos libremente ("trabajo en of0104, FS3602A y SE32") →
    (conocidos en la base global, con forma de código pero inexistentes).
    """
    known, unknown = [], []
    for token in re.split(r"[\s,;/|]+", text.upper()):
        token = token.strip(".:()[]\"'¿?¡!")
        if not token or token in known or token in unknown or is_special_code(token):
            continue
        if token in status:
            known.append(token)
        elif CODE_RE.match(token):
            unknown.append(token)
    return known, unknown


def legacy_codes(xlsx_path: str) -> List[str]:
    """Códigos del Excel de proyectos antiguo (Include = 1, sin XX) para importarlos una vez."""
    df = pd.read_excel(xlsx_path, sheet_name=LEGACY_DB_SHEET)
    if 'Include' in df.columns:
        df = df[pd.to_numeric(df['Include'], errors='coerce').fillna(1) == 1]
    out = []
    for c in df['Code']:
        if _is_empty(c) or isinstance(c, (int, float)) or is_special_code(c):
            continue
        code = str(c).strip().upper()
        if code not in out:
            out.append(code)
    return out


def find_task(task_details_path: str, code: str) -> Optional[dict]:
    """Un código de la base global (None si no existe)."""
    return task_status(task_details_path).get(str(code).strip().upper())
