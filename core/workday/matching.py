# ============================================================
# ELECCIÓN DEL TIPO DE JORNADA CUANDO WORKDAY DEVUELVE VARIAS OPCIONES
# ============================================================
import re
from difflib import SequenceMatcher


def option_task(label: str) -> str:
    """'PRJ005746 X > Marco de referencia > IS General Admin (Comienza el: …)' → 'IS General Admin'."""
    label = re.sub(r"\s*\([^()]*\)\s*$", "", " ".join(label.split()))
    return label.split(">")[-1].strip()


def best_option(task_name: str, labels: list) -> tuple:
    """Índice de la opción cuyo último tramo coincide más con el Task Name, y su coincidencia (0–1)."""
    want = " ".join(task_name.split()).lower()
    scores = [1.0 if option_task(l).lower() == want
              else SequenceMatcher(None, want, option_task(l).lower()).ratio()
              for l in labels]
    best = max(range(len(labels)), key=lambda i: scores[i])
    return best, scores[best]


def week_label_matches(label: str, week_start: str) -> bool:
    """¿La etiqueta de una semana ('27/09/2026 - 03/10/2026') empieza en week_start ('YYYY-MM-DD')?
    Acepta DD/MM/YYYY y MM/DD/YYYY (y separadores - o .) para no depender del idioma."""
    m = re.search(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", label or "")
    if not m:
        return False
    a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    yy, mm, dd = (int(x) for x in week_start.split("-"))
    return y == yy and ((a, b) == (dd, mm) or (a, b) == (mm, dd))


def week_months(week_start: str) -> list:
    """Meses (año, mes) del calendario donde Workday ofrece la semana: el del domingo y, si cruza, el del sábado."""
    from datetime import date, timedelta
    sun = date.fromisoformat(week_start)
    sat = sun + timedelta(days=6)
    return list(dict.fromkeys([(sun.year, sun.month), (sat.year, sat.month)]))
