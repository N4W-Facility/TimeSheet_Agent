# ============================================================
# PERIODOS Y VALIDACIONES DE LA HOJA DE TIEMPO
# Ojo: N4W usa semanas lunes–domingo; Workday agrupa domingo–sábado
# (ver core/workday/csv_reader.py).
# ============================================================
from datetime import datetime, timedelta

import pandas as pd

from core.utils import get_date_columns


def align_to_full_weeks(start: datetime, end: datetime) -> tuple:
    """Expande el rango a semanas completas lunes–domingo (requisito de N4W)."""
    start = start - timedelta(days=start.weekday())
    end = end + timedelta(days=6 - end.weekday())
    return start, end


def month_bounds(year: int, month: int) -> tuple:
    """Primer y último día del mes calendario (periodo de Workday)."""
    first = datetime(year, month, 1)
    last = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    return first, last


def weeks_touching(start: datetime, end: datetime) -> list:
    """Semanas lunes–domingo que tocan el rango (candidatas para N4W): [(lunes, domingo)]."""
    first, last = align_to_full_weeks(start, end)
    weeks = []
    while first <= last:
        weeks.append((first, first + timedelta(days=6)))
        first += timedelta(days=7)
    return weeks


def validate_complete_weeks(start: datetime, end: datetime) -> tuple:
    """(is_valid, error) — el rango debe ir de lunes a domingo."""
    if start.weekday() != 0:
        return False, f"Start date must be a Monday (it is a {start.strftime('%A')})."
    if end.weekday() != 6:
        return False, f"End date must be a Sunday (it is a {end.strftime('%A')})."
    days = (end - start).days + 1
    if days % 7 != 0:
        return False, f"Range must be complete weeks ({days} days)."
    return True, ""


def timesheet_date_range(df: pd.DataFrame) -> tuple:
    """(primera, última) fecha de las columnas de un timesheet."""
    dates = sorted(datetime.strptime(str(c).split(' ')[0], '%Y-%m-%d') for c in get_date_columns(df))
    if not dates:
        raise ValueError("The timesheet has no date columns.")
    return dates[0], dates[-1]


def daily_totals(df: pd.DataFrame) -> pd.Series:
    """Horas totales por día (index = 'YYYY-MM-DD')."""
    cols = get_date_columns(df)
    totals = df[cols].sum()
    totals.index = [str(c).split(' ')[0] for c in totals.index]
    return totals


def find_irregular_days(df: pd.DataFrame, expected: float = 8.0) -> list:
    """
    Días laborables con total distinto de `expected` y fines de semana con horas.
    Returns: [{'date', 'hours', 'issue'}]
    """
    issues = []
    for date_str, hours in daily_totals(df).items():
        weekday = datetime.strptime(date_str, '%Y-%m-%d').weekday()
        if weekday < 5 and abs(hours - expected) > 0.001:
            issues.append({'date': date_str, 'hours': float(hours),
                           'issue': 'under' if hours < expected else 'over'})
        elif weekday >= 5 and hours > 0:
            issues.append({'date': date_str, 'hours': float(hours), 'issue': 'weekend'})
    return issues


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    """Resumen por código: Task Name y total de horas (para la aprobación)."""
    cols = get_date_columns(df)
    out = df.copy()
    if 'Code' in out.columns:
        out = out.set_index('Code')
    out['Total'] = out[cols].sum(axis=1)
    out = out[out['Total'] > 0]
    keep = [c for c in ('Task Name', 'Total') if c in out.columns]
    return out[keep].sort_values('Total', ascending=False)
