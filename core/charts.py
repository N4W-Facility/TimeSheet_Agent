# ============================================================
# GRÁFICAS DEL ANÁLISIS
#   *_chart(...)     → spec (dict) con los datos, sin librerías gráficas (testeable)
#   mpl_figure(spec) → figura matplotlib para la tarjeta del chat (hover con mplcursors)
#   open_interactive(spec) → HTML plotly en el navegador (zoom, filtrar series, exportar)
# spec = {'kind', 'title', 'x': [...], 'series': [{'name', 'values'}], 'lines': [{'name', 'values'}]}
# kind: stacked (barras apiladas) | grouped (barras lado a lado) | donut | daily | trend
# ============================================================
import os
import re
import webbrowser
from datetime import datetime
from typing import List, Optional

import pandas as pd

from core.analysis import by_project, monthly

TOP = 7                     # proyectos con color propio; el resto va a "Other"
OTHER = "Other"
PALETTE = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#a855f7", "#06b6d4", "#ec4899", "#84cc16"]
OTHER_COLOR = "#71717a"
BG, FG, GRID, MUTED = "#111113", "#fafafa", "#27272a", "#a1a1aa"


def _top_codes(df: pd.DataFrame, n: int = TOP) -> List[str]:
    return list(by_project(df).index[:n])


def _color(name: str, i: int) -> str:
    return OTHER_COLOR if name == OTHER else PALETTE[i % len(PALETTE)]


# ── Datos ────────────────────────────────────────────────────

def months_chart(df: pd.DataFrame, title: str = "Hours per month by project") -> dict:
    """Barras apiladas: un mes por barra, un color por proyecto."""
    pivot = monthly(df)                                   # código × mes
    top = _top_codes(df)
    rows = pivot.loc[[c for c in top if c in pivot.index]]
    rest = pivot.drop(index=rows.index)
    series = [{'name': c, 'values': [round(float(v), 2) for v in rows.loc[c]]} for c in rows.index]
    if not rest.empty:
        series.append({'name': OTHER, 'values': [round(float(v), 2) for v in rest.sum()]})
    return {'kind': 'stacked', 'title': title, 'x': list(pivot.columns), 'series': series, 'lines': []}


def share_chart(df: pd.DataFrame, title: str) -> dict:
    """Distribución del periodo por proyecto (dona)."""
    bp = by_project(df)
    top = bp.iloc[:TOP]
    x, values = list(top.index), [round(float(v), 2) for v in top['Hours']]
    if len(bp) > TOP:
        x.append(OTHER)
        values.append(round(float(bp['Hours'].iloc[TOP:].sum()), 2))
    return {'kind': 'donut', 'title': title, 'x': x, 'series': [{'name': 'Hours', 'values': values}],
            'lines': []}


def daily_chart(df: pd.DataFrame, start: datetime, end: datetime, daily: float, title: str) -> dict:
    """Total por día frente a lo esperado; los días laborables sin horas quedan marcados."""
    days = pd.date_range(start, end)
    totals = df.groupby('day')['hours'].sum()
    x = [f"{d:%Y-%m-%d}" for d in days]
    values = [round(float(totals.get(d, 0.0)), 2) for d in x]
    missing = [d for d, v, dt in zip(x, values, days) if v == 0 and dt.weekday() < 5]
    return {'kind': 'daily', 'title': title, 'x': x, 'series': [{'name': 'Hours', 'values': values}],
            'lines': [{'name': f'Expected ({daily:g} h)', 'values': [daily if dt.weekday() < 5 else 0
                                                                     for dt in days]}],
            'missing': missing}


def trend_chart(df: pd.DataFrame, code: str, target: Optional[dict] = None) -> Optional[dict]:
    """Horas de un proyecto mes a mes, con su promedio y su objetivo (si hay)."""
    pivot = monthly(df)
    if code not in pivot.index:
        return None
    values = [round(float(v), 2) for v in pivot.loc[code]]
    lines = [{'name': 'Average', 'values': [round(sum(values) / len(values), 2)] * len(values)}]
    if target and target.get('hours') is not None:
        lines.append({'name': 'Target', 'values': [float(target['hours'])] * len(values)})
    elif target and target.get('pct') is not None:
        totals = pivot.sum(axis=0)
        lines.append({'name': f"Target ({target['pct']:g}%)",
                      'values': [round(float(t) * target['pct'] / 100, 2) for t in totals]})
    return {'kind': 'trend', 'title': f"{code} — hours per month", 'x': list(pivot.columns),
            'series': [{'name': code, 'values': values}], 'lines': lines}


def compare_chart(df_a: pd.DataFrame, df_b: pd.DataFrame, label_a: str, label_b: str) -> dict:
    """Barras lado a lado por proyecto para dos periodos."""
    a, b = by_project(df_a)['Hours'], by_project(df_b)['Hours']
    codes = list((a.add(b, fill_value=0)).sort_values(ascending=False).index[:TOP + 3])
    return {'kind': 'grouped', 'title': f"{label_a} vs {label_b}", 'x': codes,
            'series': [{'name': label_a, 'values': [round(float(a.get(c, 0)), 2) for c in codes]},
                       {'name': label_b, 'values': [round(float(b.get(c, 0)), 2) for c in codes]}],
            'lines': []}


# ── Matplotlib (tarjeta del chat) ────────────────────────────

def mpl_figure(spec: dict):
    """Figura para incrustar en Tk. Devuelve (fig, artists) — artists con hover."""
    from matplotlib.figure import Figure

    fig = Figure(figsize=(6.2, 3.2), dpi=100, facecolor=BG)
    ax = fig.add_subplot(111, facecolor=BG)
    kind, x = spec['kind'], spec['x']
    artists = []

    if kind == 'donut':
        s = spec['series'][0]
        wedges, _ = ax.pie(s['values'], colors=[_color(n, i) for i, n in enumerate(x)], startangle=90,
                           counterclock=False, wedgeprops={'width': 0.38, 'edgecolor': BG})
        total = sum(s['values']) or 1
        for w, name, v in zip(wedges, x, s['values']):
            w.set_gid(f"{name}: {v:g} h ({v / total * 100:.0f}%)")
            artists.append(w)
        ax.legend(wedges, x, loc='center left', bbox_to_anchor=(1, 0.5), frameon=False,
                  labelcolor=FG, fontsize=8)
        ax.text(0, 0, f"{total:g} h", ha='center', va='center', color=FG, fontsize=11, weight='bold')
        ax.set_aspect('equal')
    else:
        pos = list(range(len(x)))
        if kind == 'stacked':
            bottom = [0.0] * len(x)
            for i, s in enumerate(spec['series']):
                bars = ax.bar(pos, s['values'], bottom=bottom, color=_color(s['name'], i), label=s['name'],
                              width=0.7)
                for bar, v, px in zip(bars, s['values'], x):
                    bar.set_gid(f"{s['name']} · {px}: {v:g} h")
                artists += list(bars)
                bottom = [b + v for b, v in zip(bottom, s['values'])]
        elif kind == 'grouped':
            n, width = len(spec['series']), 0.8 / max(1, len(spec['series']))
            for i, s in enumerate(spec['series']):
                bars = ax.bar([p - 0.4 + width * (i + 0.5) for p in pos], s['values'], width=width,
                              color=PALETTE[i], label=s['name'])
                for bar, v, px in zip(bars, s['values'], x):
                    bar.set_gid(f"{px} · {s['name']}: {v:g} h")
                artists += list(bars)
        elif kind == 'daily':
            missing = set(spec.get('missing', []))
            s = spec['series'][0]
            bars = ax.bar(pos, s['values'], color=[PALETTE[0]] * len(x), width=0.75, label='Hours')
            for bar, v, px in zip(bars, s['values'], x):
                bar.set_gid(f"{px}: {v:g} h" + ("  ⚠ no hours" if px in missing else ""))
                if px in missing:
                    bar.set_height(0.25)
                    bar.set_color(PALETTE[3])
            artists += list(bars)
        elif kind == 'trend':
            s = spec['series'][0]
            line, = ax.plot(pos, s['values'], marker='o', color=PALETTE[0], label=s['name'])
            line.set_gid([f"{px}: {v:g} h" for px, v in zip(x, s['values'])])
            artists.append(line)
        for i, ln in enumerate(spec['lines']):
            ax.plot(pos, ln['values'], linestyle='--', linewidth=1.2, label=ln['name'],
                    color=[MUTED, PALETTE[2], PALETTE[1]][i % 3],
                    drawstyle='steps-mid' if kind == 'daily' else 'default')
        step = max(1, len(x) // 12)
        ax.set_xticks(pos[::step])
        ax.set_xticklabels([str(v)[5:] if kind == 'daily' else str(v) for v in x[::step]],
                           rotation=45 if len(x) > 6 else 0, ha='right' if len(x) > 6 else 'center')
        ax.set_ylabel('h', color=MUTED)
        ax.tick_params(colors=MUTED, labelsize=8)
        ax.grid(axis='y', color=GRID, linewidth=0.6)
        ax.set_axisbelow(True)
        for side in ax.spines.values():
            side.set_color(GRID)
        ax.legend(loc='upper left', bbox_to_anchor=(1, 1), frameon=False, labelcolor=FG, fontsize=8)
    fig.tight_layout()
    return fig, artists


def attach_hover(artists):
    """Valor al pasar el mouse (mplcursors). Sin la librería, la gráfica igual se muestra."""
    try:
        import mplcursors
    except ImportError:
        return None
    cursor = mplcursors.cursor(artists, hover=True)

    @cursor.connect("add")
    def _(sel):
        gid = sel.artist.get_gid()
        text = gid[int(round(sel.index))] if isinstance(gid, list) else gid
        sel.annotation.set_text(text or "")
        sel.annotation.get_bbox_patch().set(fc=GRID, ec=MUTED, alpha=0.95)
        sel.annotation.set_color(FG)
        sel.annotation.set_fontsize(9)
    return cursor


# ── Plotly (navegador) ───────────────────────────────────────

def plotly_figure(spec: dict):
    import plotly.graph_objects as go

    kind, x = spec['kind'], spec['x']
    fig = go.Figure()
    if kind == 'donut':
        s = spec['series'][0]
        fig.add_trace(go.Pie(labels=x, values=s['values'], hole=0.45, sort=False,
                             marker={'colors': [_color(n, i) for i, n in enumerate(x)]},
                             hovertemplate="%{label}: %{value} h (%{percent})<extra></extra>"))
    else:
        for i, s in enumerate(spec['series']):
            if kind == 'trend':
                fig.add_trace(go.Scatter(x=x, y=s['values'], name=s['name'], mode='lines+markers',
                                         line={'color': PALETTE[0]}))
            else:
                colors = _color(s['name'], i) if kind == 'stacked' else PALETTE[i]
                if kind == 'daily':
                    missing = set(spec.get('missing', []))
                    colors = [PALETTE[3] if d in missing else PALETTE[0] for d in x]
                fig.add_trace(go.Bar(x=x, y=s['values'], name=s['name'], marker={'color': colors},
                                     hovertemplate="%{x}: %{y} h<extra>" + s['name'] + "</extra>"))
        for i, ln in enumerate(spec['lines']):
            fig.add_trace(go.Scatter(x=x, y=ln['values'], name=ln['name'], mode='lines',
                                     line={'dash': 'dash', 'color': [MUTED, PALETTE[2], PALETTE[1]][i % 3],
                                           'shape': 'hvh' if kind == 'daily' else 'linear'}))
        fig.update_layout(barmode='stack' if kind == 'stacked' else 'group',
                          yaxis_title='hours', hovermode='closest')
    fig.update_layout(title=spec['title'], template='plotly_dark', paper_bgcolor=BG, plot_bgcolor=BG,
                      font={'family': 'Segoe UI, sans-serif'})
    return fig


def open_interactive(spec: dict, folder: str) -> str:
    """Escribe el HTML (plotly embebido, funciona sin internet) y lo abre en el navegador."""
    os.makedirs(folder, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9]+", "_", spec['title']).strip("_")[:60] or "chart"
    path = os.path.join(folder, f"{slug}.html")
    plotly_figure(spec).write_html(path, include_plotlyjs=True, full_html=True)
    webbrowser.open(f"file:///{os.path.abspath(path).replace(os.sep, '/')}")
    return path
