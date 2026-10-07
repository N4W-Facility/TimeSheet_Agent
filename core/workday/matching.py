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
