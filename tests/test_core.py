"""Tests de las partes puras (no requieren Windows, Outlook ni navegador)."""
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import analysis, database, n4w, outlook, prorate, timesheet  # noqa: E402
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

def test_month_bounds_is_calendar_month():
    assert timesheet.month_bounds(2026, 10) == (datetime(2026, 10, 1), datetime(2026, 10, 31))
    assert timesheet.month_bounds(2026, 12) == (datetime(2026, 12, 1), datetime(2026, 12, 31))


def test_weeks_touching_month_are_monday_sunday():
    weeks = timesheet.weeks_touching(*timesheet.month_bounds(2026, 10))
    assert weeks[0] == (datetime(2026, 9, 28), datetime(2026, 10, 4))
    assert weeks[-1] == (datetime(2026, 10, 26), datetime(2026, 11, 1))
    assert all(timesheet.validate_complete_weeks(m, s)[0] for m, s in weeks)


def test_validate_complete_weeks_rejects_partial():
    ok, _ = timesheet.validate_complete_weeks(datetime(2026, 10, 1), datetime(2026, 10, 31))
    assert not ok


def test_irregular_days():
    df = pd.DataFrame({'Code': ['A', 'B'],
                       '2026-10-05 00:00:00': [4, 4],     # lunes, 8h OK
                       '2026-10-06 00:00:00': [3, 0],     # martes, faltan
                       '2026-10-10 00:00:00': [1, 0]})    # sábado
    issues = {i['date']: i['issue'] for i in timesheet.find_irregular_days(df)}
    assert issues == {"2026-10-06": "under", "2026-10-10": "weekend"}


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
    # Workday agrupa domingo–sábado: el domingo 11 cae en otra semana, pero sin horas → no se incluye.
    assert list(weeks) == ['2026-10-04']
    assert weeks['2026-10-04'][0]['hours']['05-10-2026'] == 2.5
    assert format_hours(2.5) == "2,5"


# ── análisis e historial ─────────────────────────────────────

from core import analysis  # noqa: E402
from core.history import History  # noqa: E402


def wide(month_days, rows):
    """rows: {code: horas por día} → timesheet ancho para los días dados."""
    df = pd.DataFrame({'Code': list(rows), 'Task Name': [f"{c} task" for c in rows]})
    for d in month_days:
        df[f"{d} 00:00:00"] = list(rows.values())
    return df


def test_balance_by_project_and_expected_hours():
    df = analysis.to_long(wide(['2026-10-05', '2026-10-06'], {'A': 6.0, 'B': 2.0}))
    table = analysis.by_project(df)
    assert table.loc['A', 'Hours'] == 12 and table.loc['A', '%'] == 75.0 and table.loc['A', 'Days'] == 2
    text = analysis.balance_text(df, datetime(2026, 10, 5), datetime(2026, 10, 6))
    assert "TOTAL: 16 h" in text and "expected: 16 h" in text


def test_history_prefers_prorated_and_replaces_period(tmp_path):
    store = History(str(tmp_path / "h.db"))
    store.save(wide(['2026-10-05'], {'A': 6.0, 'V': 2.0}), 'outlook')
    assert set(store.hours('2026-10-01', '2026-10-31')['code']) == {'A', 'V'}
    store.save(wide(['2026-10-05'], {'A': 8.0}), 'prorated')
    assert store.hours('2026-10-01', '2026-10-31')[['code', 'hours']].values.tolist() == [['A', 8.0]]
    store.save(wide(['2026-10-05'], {'A': 4.0}), 'outlook')      # releer reemplaza
    store.clear('2026-10-01', '2026-10-31', 'prorated')
    assert store.hours('2026-10-01', '2026-10-31')['hours'].sum() == 4.0


def test_targets_merge(tmp_path):
    store = History(str(tmp_path / "h.db"))
    store.set_target('A', pct=30)
    store.set_target('A', hours=40)
    assert store.targets() == {'A': {'pct': 30.0, 'hours': 40.0}}


def test_averages_count_missing_months_as_zero():
    df = pd.concat([analysis.to_long(wide(['2026-08-03'], {'A': 8.0})),
                    analysis.to_long(wide(['2026-09-01'], {'A': 4.0, 'B': 4.0}))])
    avg = analysis.project_averages(df)
    assert avg.loc['A', 'Avg h'] == 6.0 and avg.loc['B', 'Avg h'] == 2.0
    assert avg.loc['B', 'Avg %'] == 25.0


def test_alerts_target_total_and_new_project():
    prev = analysis.to_long(wide(['2026-09-01'], {'A': 8.0}))
    cur = analysis.to_long(wide(['2026-10-05'], {'A': 2.0, 'N': 4.0}))
    notes = analysis.alerts(cur, datetime(2026, 10, 5), datetime(2026, 10, 5), prev,
                            {'A': {'pct': 80.0, 'hours': None}})
    text = "\n".join(notes)
    assert "below the expected 8 h" in text
    assert "A: 33.3% of the period vs target 80%" in text
    assert "N: new project" in text


def test_prorate_comparison_stats():
    before = wide(['2026-10-05'], {'A': 6.0, 'V': 2.0})
    after = wide(['2026-10-05'], {'A': 8.0})
    text = analysis.prorate_comparison(before, after, ['V'])
    assert "TOTAL: 8 h → 8 h" in text and "Redistributed: 2 h from V to 1 project(s)" in text


# ── base global y mis proyectos ──────────────────────────────

def _details(tmp_path):
    path = tmp_path / "details.xlsx"
    pd.DataFrame({
        'Task_Name': ['OF0104', 'FS3602A', 'SE2701', 'VI0001'],
        'Task_Name_Description': ['Overhead', 'Meta Ohio', 'Allegheny', 'Virtual'],
        'WD_TaskName': ['OF T', 'FS T', 'SE T', 'VI T'],
        'WD_GrantID': ['G1', 'G2', 'G3', 'G4'],
        'Date_Opened': ['2020-01-01', '2025-01-01', '2024-07-01', '2020-01-01'],
        'Date_Closed': [None, None, '2025-03-31', None],
        'Prorate': [0, 0, 0, 1],
    }).to_excel(path, index=False)
    return str(path)


def test_task_status_and_catalog(tmp_path):
    path = _details(tmp_path)
    status = database.task_status(path)
    assert status['SE2701']['status'] == 'closed' and status['SE2701']['closed'] == '2025-03-31'
    assert status['VI0001']['prorate'] and status['FS3602A']['description'] == 'Meta Ohio'
    cat = database.catalog(path).set_index('Code')
    assert cat.loc['FS3602A', 'Category'] == 'FS3602A | Meta Ohio'
    assert cat.loc['XX09', 'Task Name'] == 'Vacation (Days)'       # internos siempre presentes


def test_extract_codes_from_free_text(tmp_path):
    status = database.task_status(_details(tmp_path))
    known, unknown = database.extract_codes("trabajo en of0104, FS3602A y AB1234; también XX01.", status)
    assert known == ['OF0104', 'FS3602A'] and unknown == ['AB1234']


def test_review_projects_rules():
    status = {'A1000': {'status': 'active'}, 'B2000': {'status': 'closed', 'closed': '2026-08-31'},
              'C3000': {'status': 'active'}, 'D4000': {'status': 'active'}}
    hist = pd.DataFrame({'day': ['2026-08-03', '2026-09-01'], 'code': ['A1000', 'A1000'],
                         'task_name': ['', ''], 'hours': [8.0, 8.0]})
    charged = pd.DataFrame({'day': ['2026-09-01'], 'code': ['D4000'], 'task_name': [''], 'hours': [4.0]})
    props = analysis.review_projects(['A1000', 'B2000', 'C3000', 'Z9999'], status, hist, charged, 2,
                                     {'C3000': '2026-01-01'})
    got = {(p['code'], p['reason']) for p in props}
    assert got == {('B2000', 'closed'), ('C3000', 'idle'), ('Z9999', 'missing'), ('D4000', 'unlisted')}


def test_workday_picks_best_matching_option():
    from core.workday.matching import best_option, option_task
    labels = ['PRJ005611 MS Sound Coffee Island-US-AL > Marco de referencia > Admin (Comienza el: 01/07/2010)',
              'PRJ005746 N4W Implementation Support-PFW > Marco de referencia > IS General Admin '
              '(Comienza el: 01/08/2023)']
    assert option_task(labels[1]) == 'IS General Admin'
    assert best_option('IS General Admin', labels) == (1, 1.0)
    idx, score = best_option('IS General Admn', labels)            # sin coincidencia exacta
    assert idx == 1 and score < 1.0


def test_workday_week_label_any_date_format():
    from core.workday.matching import week_label_matches
    assert week_label_matches('27/09/2026 - 03/10/2026', '2026-09-27')       # es / pt
    assert week_label_matches('09/27/2026 - 10/03/2026', '2026-09-27')       # en-US
    assert not week_label_matches('04/10/2026 - 10/10/2026', '2026-09-27')
    assert not week_label_matches('27/09/2025 - 03/10/2025', '2026-09-27')
    assert not week_label_matches('', '2026-09-27')


def test_workday_week_months_crossing():
    from core.workday.matching import week_months
    assert week_months('2026-10-04') == [(2026, 10)]
    assert week_months('2026-09-27') == [(2026, 9), (2026, 10)]
    assert week_months('2026-12-27') == [(2026, 12), (2027, 1)]


def test_workday_csv_skips_weeks_without_hours(tmp_path):
    p = tmp_path / "t.csv"
    p.write_text("Code,Task Name,Grant ID,2026-10-01,2026-10-02,2026-10-05,2026-10-06\n"
                 "A1,Task A,0,8,0,0,0\n"          # solo semana del 27/09
                 "B2,Task B,0,0,0,4,4\n")         # solo semana del 04/10
    weeks = parse_csv(str(p))
    assert [x['task_name'] for x in weeks['2026-09-27']] == ['Task A']
    assert [x['task_name'] for x in weeks['2026-10-04']] == ['Task B']


def test_workday_parse_hours_cell():
    from core.workday.csv_reader import parse_hours
    assert parse_hours('7,25') == 7.25
    assert parse_hours('8') == 8.0
    assert parse_hours('') == 0.0


def test_invalid_hours_respects_open_and_close_dates():
    df = pd.DataFrame({'code': ['A1', 'A1', 'B2', 'C3', 'D4', 'XX01'],
                       'task_name': [''] * 6,
                       'day': ['2026-08-14', '2026-08-20', '2026-08-03', '2026-08-03', '2026-08-03', '2026-08-03'],
                       'hours': [4.0, 3.0, 2.0, 1.0, 5.0, 8.0]})
    status = {'A1': {'opened': '2020-01-01', 'closed': '2026-08-15'},     # cerrado a mitad de mes
              'B2': {'opened': '2026-08-10', 'closed': None},             # abre después
              'C3': {'opened': None, 'closed': None},                     # sin abrir
              'D4': {'opened': '2020-01-01', 'closed': None}}             # activo
    got = {i['code']: (i['reason'], i['days'], i['hours']) for i in analysis.invalid_hours(df, status)}
    assert got == {'A1': ('closed', ['2026-08-20'], 3.0),
                   'B2': ('not_opened', ['2026-08-03'], 2.0),
                   'C3': ('not_opened', ['2026-08-03'], 1.0)}
    df2 = df.assign(code=['Z9'] * 6)
    assert analysis.invalid_hours(df2, status)[0]['reason'] == 'missing'


def _long(rows):
    return pd.DataFrame(rows, columns=['day', 'code', 'task_name', 'hours'])


def test_chart_specs_and_renderers():
    from core import charts
    df = _long([('2026-08-03', 'A1', '', 6.0), ('2026-08-03', 'B2', '', 2.0),
                ('2026-09-01', 'A1', '', 8.0)])
    m = charts.months_chart(df)
    assert m['x'] == ['2026-08', '2026-09']
    assert {s['name']: s['values'] for s in m['series']} == {'A1': [6.0, 8.0], 'B2': [2.0, 0.0]}
    d = charts.daily_chart(df, datetime(2026, 8, 3), datetime(2026, 8, 9), 8.0, "t")
    assert d['series'][0]['values'][:2] == [8.0, 0.0] and d['missing'] == ['2026-08-04', '2026-08-05',
                                                                            '2026-08-06', '2026-08-07']
    t = charts.trend_chart(df, 'A1', {'pct': 50, 'hours': None})
    assert t['lines'][1]['values'] == [4.0, 4.0]
    assert charts.trend_chart(df, 'ZZ') is None
    for spec in (m, d, t, charts.share_chart(df, "s"), charts.compare_chart(df, df.iloc[:1], "a", "b")):
        fig, artists = charts.mpl_figure(spec)                   # dibuja sin pantalla
        assert artists
        assert charts.plotly_figure(spec).data


def test_find_category_by_code_not_name():
    from core.database import find_category
    names = ['OF0104 | Old description', 'FS3602A | Something', 'Personal']
    assert find_category('of0104', names) == 'OF0104 | Old description'
    assert find_category('FS3602', names) is None


def test_categorize_groups_and_suggestions():
    from core import categorize
    e = lambda s, d, h, c='': {'subject': s, 'start': datetime(2026, 10, d, 9), 'hours': h, 'categories': c}
    groups = categorize.uncategorized_groups([e('Weekly sync', 5, 1.0), e('Weekly sync', 12, 1.0),
                                              e('Workshop', 7, 4.0), e('Done', 7, 1.0, 'P100 | X')])
    assert [(g['subject'], g['n'], g['hours']) for g in groups] == [('Workshop', 1, 4.0), ('Weekly sync', 2, 2.0)]
    hist = [e('Weekly sync', 1, 1, 'P100 | Old name'), e('Weekly sync', 2, 1, 'P100 | Old name, Personal'),
            e('Weekly sync', 3, 1, 'P200 | Other'), e('Lunch', 3, 1, 'Personal')]
    assert categorize.suggestions(hist, ['P100 | Project', 'P300 | Other']) == {'Weekly sync': 'P100 | Project'}


def test_n4w_summary_lists_rows_and_total():
    ts = pd.DataFrame({'Code': ['P100', 'P200'], 'Task Name': ['', ''], 'Grant ID': ['', ''],
                       '2026-10-05 00:00:00': [8, 0], '2026-10-06 00:00:00': [4.5, 3]})
    text = n4w.n4w_summary(n4w.build_n4w_rows(ts, 'a@b.org', 'A', {}))
    lines = text.splitlines()
    assert lines[0].split()[:2] == ['Week', 'Project'] and len(lines) == 4
    assert '2026-10-05' in lines[1] and '12.5' in lines[1]
    assert lines[-1].split() == ['TOTAL', '15.5']
