# ============================================================
# AYUDA PARA CATEGORIZAR REUNIONES DE OUTLOOK
# Solo reuniones SIN categoría; la sugerencia sale de cómo se categorizaron
# antes las reuniones con el mismo asunto. Funciones puras (testeables en Linux).
# ============================================================
from collections import Counter, defaultdict
from typing import Dict, List

from core.database import find_category


def uncategorized_groups(entries: List[dict]) -> List[dict]:
    """Reuniones sin categoría agrupadas por asunto (una recurrente = un grupo), de más a menos horas."""
    groups = defaultdict(lambda: {'n': 0, 'hours': 0.0, 'starts': []})
    for e in entries:
        if e['categories']:
            continue
        g = groups[e['subject']]
        g['n'] += 1
        g['hours'] += e['hours']
        g['starts'].append(e['start'])
    out = [{'subject': s, **g} for s, g in groups.items()]
    return sorted(out, key=lambda g: -g['hours'])


def suggestions(history: List[dict], choices: List[str]) -> Dict[str, str]:
    """Asunto → categoría más usada antes para ese asunto (solo entre las de mis proyectos)."""
    votes = defaultdict(Counter)
    for e in history:
        for cat in (c.strip() for c in e['categories'].split(',') if c.strip()):
            code = cat.split('|')[0].strip()
            match = find_category(code, choices)
            if match:
                votes[e['subject']][match] += 1
                break
    return {s: c.most_common(1)[0][0] for s, c in votes.items()}
