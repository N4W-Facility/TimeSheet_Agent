# ============================================================
# FLUJOS COMPLETOS (deterministas) — usados por la CLI y el agente.
# Encadenan pasos del Pipeline y aplican las reglas de periodo.
# ============================================================
from datetime import datetime, timedelta
from typing import Optional

import config
from core import analysis, timesheet
from pipeline import Cancelled, Decision, Pipeline


def findings_report(findings: dict) -> str:
    """Balance por proyecto + advertencias para la tarjeta de aprobación."""
    lines = [analysis.balance_text(analysis.to_long(findings['timesheet']),
                                   findings['start'], findings['end'],
                                   config.EXPECTED_DAILY_HOURS)]
    if findings['unmapped']:
        lines += ["", "⚠ Outlook categories without a code (NOT included):"]
        lines += [f"   {cat}: {h:g} h" for cat, h in findings['unmapped'].items()]
    if findings['irregular_days']:
        lines += ["", "⚠ Days to review:"]
        lines += [f"   {d['date']}: {d['hours']:g} h ({d['issue']})" for d in findings['irregular_days']]
    return "\n".join(lines)


def run_report(pipe: Pipeline, start: datetime, end: datetime, refresh: bool = True) -> dict:
    """Solo genera el timesheet y lo muestra (no envía nada)."""
    if refresh:
        pipe.refresh_task_details()
    findings = pipe.build_timesheet(start, end)
    pipe.cb.approve(f"Report {start:%Y-%m-%d} → {end:%Y-%m-%d}", findings_report(findings))
    return findings


def run_workday_month(pipe: Pipeline, year: int, month: int,
                      confirm_each_week: bool = True, refresh: bool = True):
    """Workday: mes calendario completo. Prorratea si hay proyectos Prorate=1 (obligatorio)."""
    start, end = timesheet.month_bounds(year, month)
    if refresh:
        pipe.refresh_task_details()
    findings = pipe.build_timesheet(start, end)
    csv_path = findings['path']
    if pipe.virtual_projects(csv_path):
        csv_path = pipe.prorate(csv_path, start, end)
    pipe._approve(f"Fill Workday {start:%Y-%m-%d} → {end:%Y-%m-%d}?", findings_report(findings))
    pipe.fill_workday(csv_path, confirm_each_week=confirm_each_week)


def choose_n4w_weeks(pipe: Pipeline, year: int, month: int) -> tuple:
    """Pregunta qué semanas lun–dom del mes enviar a N4W. Deben ser consecutivas."""
    first, last = timesheet.month_bounds(year, month)
    weeks = timesheet.weeks_touching(first, last)
    labels = [f"{m:%Y-%m-%d} → {s:%Y-%m-%d}" for m, s in weeks]
    chosen = pipe.cb.decide(Decision(
        kind='n4w_weeks',
        question="Which Monday–Sunday weeks should be submitted to N4W Facility?",
        options=labels, multi=True,
    ))
    if not chosen:
        raise Cancelled("No N4W weeks selected")
    idx = sorted(labels.index(c) for c in chosen)
    if idx != list(range(idx[0], idx[-1] + 1)):
        raise ValueError("N4W weeks must be consecutive.")
    return weeks[idx[0]][0], weeks[idx[-1]][1]


def run_n4w(pipe: Pipeline, start: datetime, end: datetime, refresh: bool = True) -> str:
    """N4W: semanas completas lunes–domingo (sin prorrateo)."""
    ok, err = timesheet.validate_complete_weeks(start, end)
    if not ok:
        raise ValueError(err)
    if refresh:
        pipe.refresh_task_details()
    findings = pipe.build_timesheet(start, end)
    pipe._approve(f"N4W {start:%Y-%m-%d} → {end:%Y-%m-%d}: hours OK?", findings_report(findings))
    return pipe.submit_n4w(findings['path'], start, end)


def parse_month(value: str) -> tuple:
    """'2026-10' → (2026, 10)"""
    y, m = map(int, value.split('-'))
    if not 1 <= m <= 12:
        raise ValueError(f"Invalid month: {value}")
    return y, m


def parse_weeks(start: str, end: str) -> tuple:
    """Fechas 'YYYY-MM-DD' → rango ajustado a lunes–domingo."""
    s = datetime.strptime(start, '%Y-%m-%d')
    e = datetime.strptime(end, '%Y-%m-%d')
    return timesheet.align_to_full_weeks(s, e)
