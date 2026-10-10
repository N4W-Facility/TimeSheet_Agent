"""
Buscador de proyectos de N4W_Task_Details por programa, nombre o fase.

Los códigos siguen una lógica: programa (SE35 = Sava) + fase (01 scoping, 02 delivery,
03 knowledge), a veces con letras al final (FS3602A, SE3202KM). "agrega el proyecto de
Sava" o "la fase de scoping de Sava" se buscan sin que el usuario sepa el código.
"""
import difflib
import re
from typing import Dict, List, Optional

from agent.suggest import _norm

# Palabras de la fase (es/en/pt) → dígitos de la fase en el código (la 03 se nombra "KM")
PHASES = {
    "01": ["scoping", "scouping", "scopping", "alcance", "escopo", "fase 1", "phase 1", "fase 01"],
    "02": ["delivery", "entrega", "implementacion", "implementation", "ejecucion", "execution",
           "implementacao", "execucao", "fase 2", "phase 2", "fase 02"],
    "03": ["knowledge management", "gestion del conocimiento", "gestao do conhecimento", "km",
           "knowledge", "knowlegement", "knowledgement", "conocimiento", "conhecimento",
           "fase 3", "phase 3", "fase 03"],
}
_PHASE_WORD = {w.split()[0]: ph for ph, words in PHASES.items() for w in words if " " not in w}

# Palabras del pedido que no describen al proyecto
STOP = set("""
agrega agregar agregame anade anadir anademe suma sumar busca buscar buscame encuentra encontrar quiero
quisiera necesito puedes podrias me mi mis el la los las lo de del al a en con un una unos unas y o que
cual cuales hay abiertos abierto proyecto proyectos fase etapa porfa favor por trabajo trabajar trabajando
voy estoy tambien nuevo nueva
add find search look for the a an of my me to on in and or project projects phase please i want work
working am also new which open there are is
adiciona adicionar adicione procura procurar procure quero os as do da dos das um uma meu meus projeto
projetos etapa trabalho trabalhar estou tambem novo
""".split())


def project_phase(code: str, info: dict) -> Optional[str]:
    """Fase del proyecto: por el nombre ("Sava Scoping") o, si no lo dice, por los dígitos del código."""
    for word in re.findall(r"[a-z]+", _norm(info.get('description', ''))):
        if word in _PHASE_WORD:
            return _PHASE_WORD[word]
    m = re.match(r"^[A-Z]{2}\d{2}(\d{2})", code)
    return m.group(1) if m and m.group(1) in PHASES else None


def parse_query(text: str) -> tuple:
    """(palabras que describen al proyecto, fase pedida o None)."""
    norm = _norm(text)
    phase = None
    for ph, words in PHASES.items():
        for w in words:
            if re.search(rf"\b{w}\b", norm):
                phase = ph
                norm = re.sub(rf"\b{w}\b", " ", norm)
    words = [w for w in re.findall(r"[a-z0-9]+", norm) if w not in STOP and len(w) > 1]
    return words, phase


def _matches(word: str, code: str, haystack: List[str]) -> bool:
    if re.match(r"^[a-z]{2}\d", word):                     # programa o código parcial: "se35"
        return code.lower().startswith(word)
    if word in haystack:
        return True
    return len(word) >= 4 and bool(difflib.get_close_matches(word, haystack, n=1, cutoff=0.75))


def search(text: str, status: Dict[str, dict]) -> List[str]:
    """
    Códigos que coinciden con el pedido: todas las palabras (si ninguno las tiene todas,
    cualquiera) y, si se nombra una fase, solo esa fase. Vacío si no hay nada que buscar.
    """
    words, phase = parse_query(text)
    if not words:
        return []
    hay = {code: re.findall(r"[a-z0-9]+", _norm(f"{info.get('description', '')} {info.get('task_name', '')}"))
           for code, info in status.items()}
    hits = {code: sum(_matches(w, code, h) for w in words) for code, h in hay.items()}
    best = [c for c, n in hits.items() if n == len(words)] or [c for c, n in hits.items() if n]
    if phase:
        best = [c for c in best if project_phase(c, status[c]) == phase]
    return sorted(best)
