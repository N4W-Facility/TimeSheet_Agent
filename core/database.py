# ============================================================
# BASE DE DATOS DE CÓDIGOS N4W (Excel local + archivo de Box)
# ============================================================
import logging
import os

import pandas as pd
import requests

from config import DB_PASSWORD, DB_SHEET
from core.utils import is_special_code

log = logging.getLogger(__name__)


def download_box_file(url_box: str, output_path: str) -> str:
    """Descarga el archivo N4W_Task_Details.xlsx desde un enlace compartido de Box."""
    url_descarga = url_box.replace('/s/', '/shared/static/')
    response = requests.get(url_descarga, timeout=60)
    response.raise_for_status()
    with open(output_path, 'wb') as f:
        f.write(response.content)
    log.info(f"Box file downloaded: {output_path}")
    return output_path


def read_database(filepath: str) -> pd.DataFrame:
    """Lee la hoja de proyectos (Code, Description, Task Name, Grant ID, Category, Include)."""
    return pd.read_excel(filepath, sheet_name=DB_SHEET)


def _is_empty(value) -> bool:
    if value is None or pd.isna(value):
        return True
    return isinstance(value, str) and len(value.strip()) == 0


def update_database(db_path: str, box_file_path: str) -> list:
    """
    Sincroniza la BD local con el archivo de Box y elimina proyectos cerrados.
    Escribe vía Excel COM (la hoja está protegida y tiene fórmulas) → solo Windows.

    Returns:
        Lista de proyectos eliminados: [{'code', 'description', 'reason'}]
    """
    db_path = os.path.abspath(db_path)

    df_base = pd.read_excel(db_path, sheet_name=DB_SHEET)
    df_source = pd.read_excel(box_file_path)
    log.info(f"Database: {len(df_base)} rows | Box: {len(df_source)} rows")

    # ── 1) Actualizar Description / Task Name / Grant ID / Category ──
    valid_codes = {
        c for c in df_base['Code']
        if not _is_empty(c) and not is_special_code(c)
        and not (isinstance(c, (int, float)) and not isinstance(c, bool) and c == -1)
    }
    missing = valid_codes - set(df_source['Task_Name'].dropna())
    if missing:
        raise ValueError(f"Database codes not found in the Box file: {missing}")

    src = df_source.set_index('Task_Name')
    for idx in df_base.index:
        code = df_base.loc[idx, 'Code']
        if is_special_code(code):
            continue
        if not _is_empty(code) and code in src.index:
            df_base.loc[idx, 'Description'] = src.loc[code, 'Task_Name_Description']
            df_base.loc[idx, 'Task Name'] = src.loc[code, 'WD_TaskName']
            df_base.loc[idx, 'Grant ID'] = src.loc[code, 'WD_GrantID']
            df_base.loc[idx, 'Category'] = f"{code} | {df_base.loc[idx, 'Description']}"
        elif _is_empty(code):
            for col in ('Description', 'Task Name', 'Grant ID', 'Category'):
                df_base.loc[idx, col] = "0"

    # ── 2) Identificar proyectos cerrados ──
    removed, drop_idx = [], []
    for idx in df_base.index:
        code = df_base.loc[idx, 'Code']
        if is_special_code(code):
            continue
        if code == -1:
            drop_idx.append(idx)
        if not _is_empty(code) and code in src.index:
            opened = src.loc[code, 'Date_Opened'] if 'Date_Opened' in src.columns else None
            closed = src.loc[code, 'Date_Closed'] if 'Date_Closed' in src.columns else None
            reasons = []
            if _is_empty(opened):
                reasons.append("No Date_Opened")
            if not _is_empty(closed):
                reasons.append("Has Date_Closed")
            if reasons:
                removed.append({
                    'code': code,
                    'description': df_base.loc[idx, 'Description'],
                    'reason': ' | '.join(reasons),
                })
                drop_idx.append(idx)

    if drop_idx:
        df_base = df_base.drop(drop_idx).reset_index(drop=True)
        log.info(f"Projects removed from database: {len(removed)}")

    # ── 3) Escribir con una sola instancia Excel COM ──
    _write_database_com(db_path, df_base)
    log.info("Database updated")
    return removed


def _write_database_com(db_path: str, df_base: pd.DataFrame):
    import win32com.client  # solo Windows

    xl, wb = None, None
    try:
        xl = win32com.client.Dispatch("Excel.Application")
        xl.Visible = False
        xl.DisplayAlerts = False
        try:
            wb = xl.Workbooks.Open(db_path, Password=DB_PASSWORD)
        except Exception:
            wb = xl.Workbooks.Open(db_path)

        ws = wb.Worksheets(DB_SHEET)
        was_protected = ws.ProtectContents
        if was_protected:
            ws.Unprotect(DB_PASSWORD)

        for idx, row in df_base.iterrows():
            r = idx + 2  # +1 encabezado, +1 base 1
            ws.Cells(r, 1).Value = row['Code']
            ws.Cells(r, 2).Value = row['Description']
            ws.Cells(r, 3).Value = row['Task Name']
            ws.Cells(r, 4).Value = row['Grant ID']
            ws.Cells(r, 5).Value = row['Category']
            if 'Include' in df_base.columns:
                ws.Cells(r, 6).Value = row['Include']

        last_row = ws.UsedRange.Rows.Count
        rows_needed = len(df_base) + 1
        for r in range(last_row, rows_needed, -1):
            ws.Rows(r).Delete()

        if was_protected:
            ws.Protect(DB_PASSWORD)

        wb.Save()
        xl.CalculateUntilAsyncQueriesDone()
        wb.Save()
        wb.Close()
        wb = None
    except Exception:
        try:
            if wb is not None:
                wb.Close(SaveChanges=False)
        except Exception:
            pass
        raise
    finally:
        if xl is not None:
            try:
                xl.Quit()
            except Exception as e:
                log.warning(f"Error releasing Excel COM: {e}")
