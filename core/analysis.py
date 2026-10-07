# ============================================================
# ANÁLISIS DE HORAS — funciones puras sobre el formato "largo"
#   [day 'YYYY-MM-DD', code, task_name, hours]
# Todo número que ve el usuario sale de aquí (el LLM nunca calcula).
# ============================================================
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from core.utils import get_date_columns, is_special_code

LONG_COLUMNS = ['day', 'code', 'task_name', 'hours']


def h(x: float) -> str:
    """Horas legibles: 8 → '8', 7.25 → '7.25'."""
    return f"{x:.2f}".rstrip('0').rstrip('.')


def to_long(ts: pd.DataFrame) -> pd.DataFrame:
    """Timesheet ancho (Code, Task Name, fechas...) → formato largo, solo horas > 0."""
    d = ts.reset_index() if 'Code' not in ts.columns else ts.copy()
    if 'Task Name' not in d.columns:
        d['Task Name'] = ''
    cols = get_date_columns(d)
    long = d.melt(id_vars=['Code', 'Task Name'], value_vars=cols, var_name='day', value_name='hours')
    long['day'] = long['day'].astype(str).str[:10]
    long['hours'] = pd.to_numeric(long['hours'], errors='coerce').fillna(0.0)
    long = long[long['hours'] > 0].rename(columns={'Code': 'code', 'Task Name': 'task_name'})
    long['code'] = long['code'].astype(str)
    long['task_name'] = long['task_name'].fillna('').astype(str)
    return long[LONG_COLUMNS].reset_index(drop=True)


def working_days(start: datetime, end: datetime) -> int:
    """Días lunes–viernes del rango (sin festivos)."""
    return int(len(pd.bdate_range(start, end)))


def by_project(df: pd.DataFrame) -> pd.DataFrame:
    """Balance por código: Task Name, Hours, % del total, Days con horas."""
    if df.empty:
        return pd.DataFrame(columns=['Task Name', 'Hours', '%', 'Days']).rename_axis('Code')
    g = df.groupby('code').agg(**{'Task Name': ('task_name', 'last'),
                                  'Hours': ('hours', 'sum'),
                                  'Days': ('day', 'nunique')})
    g = g[g['Hours'] > 0]
    total = g['Hours'].sum()
    g['%'] = (g['Hours'] / total * 100).round(1) if total else 0.0
    g.index.name = 'Code'
    return g.sort_values('Hours', ascending=False)[['Task Name', 'Hours', '%', 'Days']]


def table_text(df: pd.DataFrame, max_name: int = 28) -> str:
    out = df.copy()
    if 'Task Name' in out.columns:
        out['Task Name'] = out['Task Name'].astype(str).str.slice(0, max_name)
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].map(h)
    return out.to_string()


def balance_text(df: pd.DataFrame, start: datetime, end: datetime,
                 daily: float = 8.0) -> str:
    """Tabla por proyecto + total frente a las horas esperadas del periodo."""
    table = by_project(df)
    total = float(table['Hours'].sum())
    days = working_days(start, end)
    expected = days * daily
    diff = total - expected
    lines = [table_text(table), "",
             f"TOTAL: {h(total)} h   |   expected: {h(expected)} h "
             f"({days} working days × {h(daily)} h)"]
    if abs(diff) > 0.001:
        lines.append(f"Difference: {'+' if diff > 0 else ''}{h(diff)} h")
    return "\n".join(lines)


def short_days(df: pd.DataFrame, start: datetime, end: datetime,
               daily: float = 8.0) -> List[tuple]:
    """Días lunes–viernes del rango con menos de `daily` horas: [('YYYY-MM-DD', horas)]."""
    totals = df.groupby('day')['hours'].sum() if not df.empty else pd.Series(dtype=float)
    out = []
    for d in pd.bdate_range(start, end):
        day = d.strftime('%Y-%m-%d')
        hours = float(totals.get(day, 0.0))
        if hours < daily - 0.001:
            out.append((day, hours))
    return out


# ── Mes a mes ────────────────────────────────────────────────

def monthly(df: pd.DataFrame) -> pd.DataFrame:
    """Horas por código (filas) y mes 'YYYY-MM' (columnas)."""
    if df.empty:
        return pd.DataFrame()
    d = df.assign(month=df['day'].str[:7])
    return d.pivot_table(index='code', columns='month', values='hours',
                         aggfunc='sum', fill_value=0.0)


def project_averages(df: pd.DataFrame) -> pd.DataFrame:
    """
    Promedios mensuales por código sobre todos los meses del historial
    (un mes sin horas en el proyecto cuenta como 0).
    Columnas: Task Name, Avg h, Avg %, Min h, Max h, Last h, Months (con horas)
    """
    pivot = monthly(df)
    if pivot.empty:
        return pd.DataFrame()
    pct = pivot.div(pivot.sum(axis=0).replace(0, float('nan')), axis=1).fillna(0) * 100
    names = df.groupby('code')['task_name'].last()
    out = pd.DataFrame({
        'Task Name': names,
        'Avg h': pivot.mean(axis=1).round(2),
        'Avg %': pct.mean(axis=1).round(1),
        'Min h': pivot.min(axis=1),
        'Max h': pivot.max(axis=1),
        'Last h': pivot[pivot.columns[-1]],
        'Months': (pivot > 0).sum(axis=1),
    })
    out.index.name = 'Code'
    return out.sort_values('Avg h', ascending=False)


def averages_text(df: pd.DataFrame, targets: Dict[str, dict]) -> str:
    avg = project_averages(df)
    if avg.empty:
        return "No history."
    avg['Target'] = [target_label(targets.get(c)) for c in avg.index]
    months = sorted(df['day'].str[:7].unique())
    return (f"History: {months[0]} → {months[-1]} ({len(months)} months)\n\n"
            + table_text(avg))


def project_text(df: pd.DataFrame, code: str, target: Optional[dict]) -> Optional[str]:
    """Detalle mes a mes de un proyecto. None si el código no tiene horas."""
    pivot = monthly(df)
    if pivot.empty or code not in pivot.index:
        return None
    totals = pivot.sum(axis=0)
    hours = pivot.loc[code]
    table = pd.DataFrame({'Hours': hours, '% of month': (hours / totals * 100).round(1),
                          'Month total': totals})
    table.index.name = 'Month'
    avg = project_averages(df).loc[code]
    lines = [f"{code} — {avg['Task Name']}", "", table_text(table), "",
             f"Average: {h(avg['Avg h'])} h/month ({h(avg['Avg %'])}%)   "
             f"min {h(avg['Min h'])} h · max {h(avg['Max h'])} h"]
    if len(hours) >= 2:
        prev = hours.iloc[:-1].mean()
        trend = hours.iloc[-1] - prev
        lines.append(f"Last month vs previous average: {'+' if trend >= 0 else ''}{h(trend)} h")
    lines.append(f"Target: {target_label(target)}")
    return "\n".join(lines)


def compare_text(df_a: pd.DataFrame, df_b: pd.DataFrame, label_a: str, label_b: str) -> str:
    a, b = by_project(df_a), by_project(df_b)
    t = pd.concat([a['Hours'].rename(label_a), b['Hours'].rename(label_b)], axis=1).fillna(0.0)
    t['Δ h'] = t[label_a] - t[label_b]
    t['Δ pts %'] = (a['%'].reindex(t.index).fillna(0) - b['%'].reindex(t.index).fillna(0)).round(1)
    t = t.reindex(t['Δ h'].abs().sort_values(ascending=False).index)
    t.index.name = 'Code'
    ta, tb = t[label_a].sum(), t[label_b].sum()
    diff = ta - tb
    lines = [table_text(t), "",
             f"TOTAL {label_a}: {h(ta)} h   |   {label_b}: {h(tb)} h   |   "
             f"Δ {'+' if diff >= 0 else ''}{h(diff)} h"]
    only_a = [c for c in t.index if t.loc[c, label_b] == 0]
    only_b = [c for c in t.index if t.loc[c, label_a] == 0]
    if only_a:
        lines.append(f"Only in {label_a}: {', '.join(only_a)}")
    if only_b:
        lines.append(f"Only in {label_b}: {', '.join(only_b)}")
    return "\n".join(lines)


# ── Objetivos y alertas ──────────────────────────────────────

def target_label(target: Optional[dict]) -> str:
    if not target:
        return "-"
    parts = []
    if target.get('pct') is not None:
        parts.append(f"{h(target['pct'])}%")
    if target.get('hours') is not None:
        parts.append(f"{h(target['hours'])} h")
    return " / ".join(parts) or "-"


def alerts(month_df: pd.DataFrame, start: datetime, end: datetime,
           previous_df: pd.DataFrame, targets: Dict[str, dict],
           daily: float = 8.0, tolerance: float = 10.0,
           avg_deviation: float = 15.0) -> List[str]:
    """
    Revisa un periodo frente a las horas esperadas, los objetivos y el
    promedio de los meses anteriores (previous_df). Devuelve mensajes.
    """
    out = []
    cur = by_project(month_df)
    total = float(cur['Hours'].sum())
    expected = working_days(start, end) * daily
    if abs(total - expected) > 0.001:
        word = "below" if total < expected else "above"
        out.append(f"⚠ Total {h(total)} h is {h(abs(total - expected))} h {word} "
                   f"the expected {h(expected)} h.")

    for code, t in sorted(targets.items()):
        actual_h = float(cur['Hours'].get(code, 0.0))
        actual_p = float(cur['%'].get(code, 0.0))
        if t.get('pct') is not None and abs(actual_p - t['pct']) > tolerance:
            out.append(f"⚠ {code}: {h(actual_p)}% of the period vs target {h(t['pct'])}%.")
        if t.get('hours') is not None and abs(actual_h - t['hours']) > max(1.0, t['hours'] * tolerance / 100):
            out.append(f"⚠ {code}: {h(actual_h)} h vs target {h(t['hours'])} h.")

    avg = project_averages(previous_df) if not previous_df.empty else pd.DataFrame()
    if not avg.empty:
        for code, row in cur.iterrows():
            if code not in avg.index:
                out.append(f"ℹ {code}: new project (no hours in previous months).")
            elif code not in targets and abs(row['%'] - avg.loc[code, 'Avg %']) > avg_deviation:
                out.append(f"ℹ {code}: {h(row['%'])}% this period vs {h(avg.loc[code, 'Avg %'])}% on average.")
        for code, row in avg.iterrows():
            if code not in cur.index and row['Avg %'] >= avg_deviation:
                out.append(f"ℹ {code}: no hours this period (usually {h(row['Avg %'])}%).")
    return out


# ── Informe por proyecto frente a la base global ─────────────

STATUS_LABEL = {'active': 'active', 'closed': '⛔ closed', 'not_opened': '⛔ not opened',
                'missing': '⛔ not in Task Details', 'internal': 'internal (XX)'}
BLOCKED = ('closed', 'not_opened', 'missing')


def invalid_hours(df: pd.DataFrame, status: Dict[str, dict]) -> List[dict]:
    """
    Horas que no se pueden subir (formato largo): proyecto inexistente, sin abrir,
    o días antes de la apertura / después del cierre. Los internos (XX) no se revisan.
    Returns: [{'code', 'reason': 'missing'|'not_opened'|'closed', 'limit', 'days', 'hours'}]
    """
    out = []
    for code, g in df.groupby('code'):
        if is_special_code(code):
            continue
        info = status.get(str(code).strip().upper())
        if not info:
            reason, limit, bad = 'missing', None, g
        elif not info.get('opened'):
            reason, limit, bad = 'not_opened', None, g
        elif (g['day'] < info['opened']).any():
            reason, limit, bad = 'not_opened', info['opened'], g[g['day'] < info['opened']]
        elif info.get('closed') and (g['day'] > info['closed']).any():
            reason, limit, bad = 'closed', info['closed'], g[g['day'] > info['closed']]
        else:
            continue                    # días dentro de la vigencia: se pueden subir
        out.append({'code': code, 'reason': reason, 'limit': limit,
                    'days': sorted(bad['day'].unique()), 'hours': float(bad['hours'].sum())})
    return out


def invalid_text(issues: List[dict]) -> str:
    """Tabla de horas bloqueadas para la tarjeta."""
    why = {'missing': 'not in Task Details', 'not_opened': 'not opened', 'closed': 'closed'}
    lines = []
    for i in issues:
        reason = why[i['reason']] + (f" ({'opens' if i['reason'] == 'not_opened' else 'since'} {i['limit']})"
                                     if i['limit'] else "")
        days = ", ".join(d[5:] for d in i['days'][:8]) + (" …" if len(i['days']) > 8 else "")
        lines.append(f"{i['code']:<10} {h(i['hours']):>6} h   {reason}\n           days: {days}")
    return "\n".join(lines)


def global_status(code: str, status: Dict[str, dict]) -> str:
    """active / closed / not_opened / missing / internal según N4W_Task_Details."""
    if is_special_code(code):
        return 'internal'
    return status.get(str(code).strip().upper(), {}).get('status', 'missing')


def _off_target(target: Optional[dict], hours: float, pct: float, tolerance: float) -> bool:
    if not target:
        return False
    if target.get('pct') is not None and abs(pct - target['pct']) > tolerance:
        return True
    return (target.get('hours') is not None
            and abs(hours - target['hours']) > max(1.0, target['hours'] * tolerance / 100))


def project_report(month_df: pd.DataFrame, previous_df: pd.DataFrame,
                   targets: Dict[str, dict], status: Dict[str, dict],
                   tolerance: float = 10.0, mine: Optional[List[str]] = None) -> tuple:
    """
    Tabla por proyecto del periodo: horas, %, desvío frente al promedio,
    objetivo y estado en la base global.
    Returns: (texto, flags) con flags = listas de códigos
      blocked (cerrado / sin abrir / inexistente), off_target, new, untargeted
      (activos sin objetivo y que no se prorratean, de más a menos horas),
      unlisted (activos con horas que no están en "mis proyectos").
    """
    cur = by_project(month_df)
    avg = project_averages(previous_df) if not previous_df.empty else pd.DataFrame()
    flags = {'blocked': [], 'off_target': [], 'new': [], 'untargeted': [], 'unlisted': []}
    vs_avg, target_col, global_col = [], [], []
    for code, row in cur.iterrows():
        if avg.empty:
            vs_avg.append('-')
        elif code not in avg.index:
            vs_avg.append('new')
            flags['new'].append(code)
        else:
            d = row['%'] - avg.loc[code, 'Avg %']
            vs_avg.append(f"{'+' if d >= 0 else ''}{h(round(d, 1))} pts")

        state = global_status(code, status)
        prorated = status.get(str(code).upper(), {}).get('prorate', False)
        unlisted = mine is not None and state == 'active' and code not in mine
        global_col.append(STATUS_LABEL[state] + (' · prorate' if prorated else '')
                          + (' · not in my list' if unlisted else ''))
        if state in BLOCKED:
            flags['blocked'].append(code)
        if unlisted:
            flags['unlisted'].append(code)

        t = targets.get(code)
        off = _off_target(t, row['Hours'], row['%'], tolerance)
        target_col.append(target_label(t) + (' ⚠' if off else ''))
        if off:
            flags['off_target'].append(code)
        elif not t and state == 'active' and not prorated:
            flags['untargeted'].append(code)

    table = cur.assign(**{'vs avg': vs_avg, 'Target': target_col, 'Global': global_col})
    return table_text(table.drop(columns=['Days'])), flags


def review_projects(mine: List[str], status: Dict[str, dict], history_df: pd.DataFrame,
                    charged_df: Optional[pd.DataFrame] = None, idle_months: int = 2,
                    added: Optional[Dict[str, str]] = None) -> List[dict]:
    """
    Cambios sugeridos a "mis proyectos":
      remove · closed   → cerrado / sin abrir en la base global
      remove · missing  → ya no existe en la base global
      remove · idle     → sin horas en los últimos `idle_months` meses del historial
                          (solo si el proyecto ya estaba en la lista entonces)
      add    · unlisted → tiene horas en charged_df, está activo y no está en la lista
    Returns: [{'action', 'code', 'reason', 'detail', ('months' | 'hours')}]
    """
    out = []
    months = sorted(history_df['day'].str[:7].unique()) if not history_df.empty else []
    recent = months[-idle_months:] if idle_months else []
    pivot = monthly(history_df)
    added = added or {}
    for code in mine:
        state = global_status(code, status)
        info = status.get(code.upper(), {})
        if state in ('closed', 'not_opened'):
            detail = f"closed {info['closed']}" if info.get('closed') else "not opened"
            out.append({'action': 'remove', 'code': code, 'reason': 'closed', 'detail': detail})
            continue
        if state == 'missing':
            out.append({'action': 'remove', 'code': code, 'reason': 'missing',
                        'detail': "not in the global list"})
            continue
        if len(recent) == idle_months and recent and added.get(code, '')[:7] <= recent[0]:
            hours = pivot.loc[code, recent].sum() if code in pivot.index else 0.0
            if hours == 0:
                out.append({'action': 'remove', 'code': code, 'reason': 'idle',
                            'detail': "no hours in " + ", ".join(recent),
                            'months': ", ".join(recent)})
    if charged_df is not None and not charged_df.empty:
        for code, row in by_project(charged_df).iterrows():
            if code in mine or global_status(code, status) != 'active':
                continue
            out.append({'action': 'add', 'code': code, 'reason': 'unlisted',
                        'detail': f"{h(row['Hours'])} h charged, not in your list",
                        'hours': f"{h(row['Hours'])} h"})
    return out


def prorate_comparison(before: pd.DataFrame, after: pd.DataFrame, virtual: List[str]) -> str:
    """Tabla antes/después del prorrateo con estadísticas."""
    b, a = by_project(to_long(before)), by_project(to_long(after))
    t = pd.concat([b['Hours'].rename('Original'), a['Hours'].rename('Prorated')], axis=1).fillna(0.0)
    t['Δ h'] = t['Prorated'] - t['Original']
    total = t['Prorated'].sum()
    t['% final'] = (t['Prorated'] / total * 100).round(1) if total else 0.0
    t = t.sort_values('Prorated', ascending=False)
    t.index.name = 'Code'
    moved = float(b['Hours'].reindex(virtual).fillna(0).sum())
    receivers = [c for c in t.index if t.loc[c, 'Δ h'] > 0]
    return "\n".join([
        table_text(t), "",
        f"TOTAL: {h(t['Original'].sum())} h → {h(total)} h",
        f"Redistributed: {h(moved)} h from {', '.join(virtual) or '-'} "
        f"to {len(receivers)} project(s)",
    ])


def prorate_explanation(before: pd.DataFrame, after: pd.DataFrame, virtual: List[str]) -> str:
    """Por qué cada proyecto recibió lo que recibió: reparto proporcional a sus propias horas."""
    b, a = by_project(to_long(before)), by_project(to_long(after))
    moved = float(b['Hours'].reindex(virtual).fillna(0).sum())
    delta = a['Hours'].sub(b['Hours'], fill_value=0.0)
    receivers = [c for c in delta.index if c not in virtual and delta[c] > 0.001]
    base = float(b['Hours'].reindex(receivers).fillna(0).sum())
    lines = [f"Rule: the {h(moved)} h of {', '.join(virtual) or '-'} are split among the projects "
             "you selected, in proportion to their own hours in the period "
             "(rounded to 0.25 h per day; the daily total is kept).", ""]
    for c in sorted(receivers, key=lambda c: -delta[c]):
        own = float(b['Hours'].get(c, 0.0))
        share = own / base * 100 if base else 0.0
        lines.append(f"{c:<10} own {h(own):>6} h = {h(round(share, 1)):>5}% of {h(base)} h  "
                     f"→ +{h(delta[c])} h")
    kept = [c for c in b.index if c not in virtual and c not in receivers and not is_special_code(c)]
    if kept:
        lines += ["", f"Not selected (unchanged): {', '.join(kept)}"]
    return "\n".join(lines)
