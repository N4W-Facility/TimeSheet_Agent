# ============================================================
# PRORRATEO: reparte horas de proyectos "virtuales" (Prorate=1)
# entre proyectos reales (Prorate=0) proporcionalmente a sus horas.
# Códigos XX quedan exceptuados (ni dan ni reciben).
# ============================================================
import logging
from typing import Dict, List

import pandas as pd

from config import DB_SHEET
from core.utils import get_date_columns, is_special_code

log = logging.getLogger(__name__)


def load_prorate_flags(task_details_path: str) -> Dict[str, int]:
    """Task_Name → Prorate (0/1) desde N4W_Task_Details.xlsx."""
    df = pd.read_excel(task_details_path)
    return dict(zip(df['Task_Name'], df['Prorate']))


def classify_projects(timesheet: pd.DataFrame, task_details_path: str) -> pd.DataFrame:
    """Agrega columna Prorate: 1 virtual, 0 real, -1 exceptuado (XX)."""
    df = timesheet.copy()
    df['Prorate'] = df['Code'].map(load_prorate_flags(task_details_path)).fillna(0).astype(int)
    df.loc[df['Code'].map(is_special_code), 'Prorate'] = -1
    return df


def real_projects(timesheet: pd.DataFrame, task_details_path: str) -> List[str]:
    """Códigos candidatos a recibir horas (para que el usuario/agente elija)."""
    df = classify_projects(timesheet, task_details_path)
    return df.loc[df['Prorate'] == 0, 'Code'].tolist()


def _weights(df_real: pd.DataFrame, date_columns: List[str]) -> pd.Series:
    total_hours = df_real[date_columns].sum(axis=1)
    total = total_hours.sum()
    if total == 0:
        return pd.Series([1 / len(df_real)] * len(df_real), index=df_real.index)
    return total_hours / total


def redistribute(timesheet: pd.DataFrame, task_details_path: str,
                 selections: Dict[str, bool], db_path: str = None) -> pd.DataFrame:
    """
    Args:
        timesheet: 02-Timesheet.csv como DataFrame (columna Code)
        selections: {code_real: True si recibe horas}. Códigos ausentes → True.
        db_path: BD del usuario, para reponer Task Name / Grant ID

    Returns:
        DataFrame [Code, Task Name, Grant ID, fechas...]
    """
    df = classify_projects(timesheet, task_details_path)
    date_columns = get_date_columns(df)
    if not date_columns:
        raise ValueError("The timesheet has no date columns.")

    df_virtual = df[df['Prorate'] == 1].copy()
    df_real = df[df['Prorate'] == 0].copy()
    df_excepted = df[df['Prorate'] == -1].copy()
    log.info(f"Virtual: {len(df_virtual)} | Real: {len(df_real)} | Excepted: {len(df_excepted)}")
    if df_real.empty:
        raise ValueError("No real projects available to receive hours.")

    df_real['Target'] = df_real['Code'].map(selections).fillna(True).astype(bool)
    df_sel = df_real[df_real['Target']].copy()
    df_not_sel = df_real[~df_real['Target']].copy()
    if df_sel.empty:
        raise ValueError("No project selected to receive hours.")

    df_result = df_sel.copy()
    weights = _weights(df_sel, date_columns)
    for _, v_row in df_virtual.iterrows():
        hours = v_row[date_columns].values
        for real_idx in df_sel.index:
            result_idx = df_result[df_result['Code'] == df_sel.loc[real_idx, 'Code']].index[0]
            df_result.loc[result_idx, date_columns] += hours * weights.loc[real_idx]

    df_result = df_result.groupby(['Code'], as_index=False)[date_columns].sum()
    df_result[date_columns] = df_result[date_columns].map(lambda x: round(x * 4) / 4)

    # Ajuste día a día para conservar el total tras redondear
    original = pd.concat([df_virtual, df_sel], ignore_index=True)[date_columns].sum()
    for col in date_columns:
        diff = original[col] - df_result[col].sum()
        if abs(diff) <= 0.001:
            continue
        for idx in df_result.sort_values(by=col, ascending=False).index:
            if diff > 0:
                df_result.loc[idx, col] = round((df_result.loc[idx, col] + diff) * 4) / 4
                break
            if df_result.loc[idx, col] >= abs(diff):
                df_result.loc[idx, col] = round((df_result.loc[idx, col] - abs(diff)) * 4) / 4
                break

    base_columns = ['Code'] + date_columns
    parts = [df_result]
    if not df_not_sel.empty:
        parts.append(df_not_sel[base_columns])
    if not df_excepted.empty:
        parts.append(df_excepted[base_columns])
    df_result = pd.concat(parts, ignore_index=True)

    if db_path:
        df_db = pd.read_excel(db_path, sheet_name=DB_SHEET)[['Code', 'Task Name', 'Grant ID']].drop_duplicates()
        df_result = df_result.merge(df_db, on='Code', how='left')
        df_result['Task Name'] = df_result['Task Name'].fillna('')
        df_result['Grant ID'] = df_result['Grant ID'].fillna('')
        df_result = df_result[['Code', 'Task Name', 'Grant ID'] + date_columns]

    # Códigos XX: horas > 0 se reportan como 1
    xx = df_result['Code'].map(is_special_code)
    for col in date_columns:
        df_result.loc[xx & (df_result[col] > 0), col] = 1

    before = df[date_columns].sum().sum()
    after = df_result[date_columns].sum().sum()
    log.info(f"Prorate: original total {before:.2f}h → final {after:.2f}h")
    return df_result
