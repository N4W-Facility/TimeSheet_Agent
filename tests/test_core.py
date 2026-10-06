"""Tests de las partes puras (no requieren Windows, Outlook ni navegador)."""
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import n4w, outlook, prorate, timesheet  # noqa: E402
from core.workday.csv_reader import format_hours, parse_csv  # noqa: E402


def make_db():
    return pd.DataFrame({
        'Code': ['OF0104', 'P100', 'XX01'],
        'Description': ['Overhead', 'Proyecto', 'Especial'],
        'Task Name': ['OF0104 Task', 'P100 Task', 'XX Task'],
        'Grant ID': ['G1', 'G2', '0'],
        'Category': ['OF0104 | Overhead', 'P100 | Proyecto', 'XX01 | Especial'],
        'Include': [1, 1, 1],
    })


# ── timesheet ────────────────────────────────────────────────

def test_month_range_aligns_to_monday_sunday():
    start, end = timesheet.month_range(2026, 10)
    assert (start, end) == (datetime(2026, 9, 28), datetime(2026, 11, 1))
    assert timesheet.validate_complete_weeks(start, end) == (True, "")


def test_validate_complete_weeks_rejects_partial():
    ok, _ = timesheet.validate_complete_weeks(datetime(2026, 10, 1), datetime(2026, 10, 31))
    assert not ok


def test_irregular_days():
    df = pd.DataFrame({'Code': ['A', 'B'],
                       '2026-10-05 00:00:00': [4, 4],     # lunes, 8h OK
                       '2026-10-06 00:00:00': [3, 0],     # martes, faltan
                       '2026-10-10 00:00:00': [1, 0]})    # sábado
    issues = {i['date']: i['issue'] for i in timesheet.find_irregular_days(df)}
    assert issues == {'2026-10-06': 'menos horas', '2026-10-10': 'fin de semana'}


# ── outlook.build_timesheet (sin COM) ────────────────────────

def test_build_timesheet_maps_codes_and_reports_unmapped():
    meetings = pd.DataFrame({
        'Date': [date(2026, 10, 5), date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 6)],
        'Category': ['P100 | Proyecto', 'OF0104 | Overhead', 'P100 | Proyecto', 'Sin Category'],
        'Hours': [5.1, 3.0, 8.0, 1.0],
    })
    ts, unmapped = outlook.build_timesheet(meetings, datetime(2026, 10, 5), datetime(2026, 10, 6), make_db())

    assert list(ts.columns) == ['Task Name', 'Grant ID', '2026-10-05 00:00:00', '2026-10-06 00:00:00']
    assert ts.loc['P100', '2026-10-05 00:00:00'] == 5.0     # redondeo a 0.25
    assert ts.loc['P100', '2026-10-06 00:00:00'] == 8.0
    assert unmapped == {'Sin Category': 1.0}


# ── prorate ──────────────────────────────────────────────────

def test_prorate_conserves_hours(tmp_path):
    details = tmp_path / "details.xlsx"
    pd.DataFrame({'Task_Name': ['V1', 'R1', 'R2'], 'Prorate': [1, 0, 0]}).to_excel(details, index=False)
    ts = pd.DataFrame({'Code': ['V1', 'R1', 'R2', 'XX01'],
                       '2026-10-05 00:00:00': [2.0, 3.0, 3.0, 0.5]})

    out = prorate.redistribute(ts, str(details), {'R1': True, 'R2': True}).set_index('Code')
    col = '2026-10-05 00:00:00'
    assert out.loc['R1', col] + out.loc['R2', col] == 8.0
    assert 'V1' not in out.index
    assert out.loc['XX01', col] == 1      # XX con horas → 1


# ── n4w ──────────────────────────────────────────────────────

def test_n4w_rows_group_monday_weeks_and_replace_xx(tmp_path):
    ts = pd.DataFrame({'Code': ['P100', 'XX01', 'TNC1'], 'Task Name': ['', '', ''], 'Grant ID': ['', '', ''],
                       '2026-10-05 00:00:00': [8, 0, 1],    # lunes
                       '2026-10-11 00:00:00': [0, 1, 0]})   # domingo misma semana
    rows = n4w.build_n4w_rows(ts, 'a@b.org', 'A', {'P100': 'TS-P100'})
    assert set(rows['new_projectcode']) == {'TS-P100', 'OF0104'}   # TNC excluido, XX→OF0104
    assert rows.set_index('new_projectcode').loc['OF0104', 'new_sunhours'] == 1
    path = n4w.write_n4w_excel(rows, str(tmp_path / 'out.xlsx'))
    assert Path(path).exists()


def test_find_overlaps():
    existing = [('f1.xlsx', date(2026, 9, 28), date(2026, 10, 4))]
    assert n4w.find_overlaps(datetime(2026, 10, 5), datetime(2026, 11, 1), existing) == []
    assert len(n4w.find_overlaps(datetime(2026, 10, 1), datetime(2026, 10, 12), existing)) == 1


# ── Workday csv_reader con salida real de build_timesheet ────

def test_workday_reads_generated_csv(tmp_path):
    meetings = pd.DataFrame({'Date': [date(2026, 10, 5)], 'Category': ['P100 | Proyecto'], 'Hours': [2.5]})
    ts, _ = outlook.build_timesheet(meetings, datetime(2026, 10, 5), datetime(2026, 10, 11), make_db())
    csv = tmp_path / '02-Timesheet.csv'
    ts.to_csv(csv, index_label='Code')

    weeks = parse_csv(str(csv))
    # Workday agrupa domingo–sábado: el domingo 11 cae en otra semana (con 0 h).
    # Comportamiento heredado; se revisará en la fase 2.
    assert list(weeks) == ['2026-10-04', '2026-10-11']
    assert weeks['2026-10-04'][0]['hours']['05-10-2026'] == 2.5
    assert weeks['2026-10-11'][0]['hours'] == {'11-10-2026': 0.0}
    assert format_hours(2.5) == "2,5"
