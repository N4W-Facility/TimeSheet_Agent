# ============================================================
# SUGERENCIAS — frases en lenguaje natural según el paso actual.
# No ejecutan nada: la UI las ofrece para autocompletar y el agente
# las cita en sus mensajes ("Siguiente paso: escribe «...»").
# Lo que el usuario envía sigue pasando por el LLM.
# ============================================================
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import List, Optional

LANGS = ("en", "es", "pt")

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "pt": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
           "agosto", "setembro", "outubro", "novembro", "dezembro"],
}

PHRASES = {
    "read":         {"en": "read my hours for {month}",
                     "es": "lee mis horas de {month}",
                     "pt": "leia minhas horas de {month}"},
    "load_history": {"en": "load my history",
                     "es": "carga mi historial",
                     "pt": "carregar meu histórico"},
    "prorate":      {"en": "prorate the hours for {month}",
                     "es": "prorratea las horas de {month}",
                     "pt": "ratear as horas de {month}"},
    "workday":      {"en": "fill Workday for {month}",
                     "es": "llena Workday de {month}",
                     "pt": "preencher o Workday de {month}"},
    "workday_period": {"en": "fill Workday with the hours I read",
                       "es": "llena Workday con las horas leídas",
                       "pt": "preencher o Workday com as horas lidas"},
    "n4w":          {"en": "submit N4W for {month}",
                     "es": "envía N4W de {month}",
                     "pt": "enviar N4W de {month}"},
    "status":       {"en": "what's pending?",
                     "es": "¿qué me falta?",
                     "pt": "o que falta?"},
    "close":        {"en": "am I ready to close {month}?",
                     "es": "¿estoy listo para cerrar {month}?",
                     "pt": "estou pronto para fechar {month}?"},
    "week_hours":   {"en": "how many hours do I have this week?",
                     "es": "¿cuántas horas llevo esta semana?",
                     "pt": "quantas horas tenho esta semana?"},
    "why_prorate":  {"en": "why did you prorate like that?",
                     "es": "¿por qué prorrateaste así?",
                     "pt": "por que você rateou assim?"},
    "edit":         {"en": "put 4 h on {code} on Tuesday",
                     "es": "pon 4 h a {code} el martes",
                     "pt": "coloque 4 h em {code} na terça"},
    "categorize":   {"en": "help me categorize my meetings of {month}",
                     "es": "ayúdame a categorizar mis reuniones de {month}",
                     "pt": "me ajude a categorizar minhas reuniões de {month}"},
    "summary":      {"en": "summary of my hours for {month}",
                     "es": "resumen de mis horas de {month}",
                     "pt": "resumo das minhas horas de {month}"},
    "compare":      {"en": "compare {month} with {prev}",
                     "es": "compara {month} con {prev}",
                     "pt": "comparar {month} com {prev}"},
    "alerts":       {"en": "any alerts for {month}?",
                     "es": "¿tengo alertas en {month}?",
                     "pt": "tenho alertas em {month}?"},
    "averages":     {"en": "show my averages per project",
                     "es": "muéstrame mis promedios por proyecto",
                     "pt": "mostrar minhas médias por projeto"},
    "project_avg":  {"en": "what is my average on {code}?",
                     "es": "¿cuál es mi promedio en {code}?",
                     "pt": "qual é minha média em {code}?"},
    "target":       {"en": "my dedication to {code} should be 30%",
                     "es": "mi dedicación a {code} debería ser 30%",
                     "pt": "minha dedicação a {code} deveria ser 30%"},
    "add_project":  {"en": "I'm also working on project ",
                     "es": "también trabajo en el proyecto ",
                     "pt": "também trabalho no projeto "},
    "remove_project": {"en": "I no longer work on {code}",
                       "es": "ya no trabajo en {code}",
                       "pt": "não trabalho mais em {code}"},
    "import_excel": {"en": "import my Excel",
                     "es": "importar mi Excel",
                     "pt": "importar meu Excel"},
    "my_projects":  {"en": "which are my projects?",
                     "es": "¿cuáles son mis proyectos?",
                     "pt": "quais são os meus projetos?"},
    "update_db":    {"en": "update the global project list",
                     "es": "actualiza la base global de proyectos",
                     "pt": "atualizar a base global de projetos"},
    "sync":         {"en": "sync my Outlook categories",
                     "es": "sincroniza mis categorías de Outlook",
                     "pt": "sincronizar minhas categorias do Outlook"},
    "chart":        {"en": "show me a chart of my hours this year",
                     "es": "muéstrame una gráfica de mis horas este año",
                     "pt": "mostre um gráfico das minhas horas este ano"},
    "help":         {"en": "what can you do?",
                     "es": "¿qué puedes hacer?",
                     "pt": "o que você pode fazer?"},
}


@dataclass
class State:
    """Foto del agente para sugerir (sin depender de agent.agent)."""
    start: Optional[datetime] = None        # periodo leído (None = nada leído)
    is_month: bool = False
    virtual: tuple = ()
    prorated: bool = False
    workday_done: bool = False
    n4w_done: bool = False                  # N4W enviado para semanas de este periodo
    has_history: bool = False
    top_code: Optional[str] = None          # proyecto principal (para ejemplos)

    @property
    def stage(self) -> str:
        if self.start is None:
            return "start"
        if self.virtual and not self.prorated:
            return "prorate"
        if not self.workday_done:
            return "workday"
        return "done"


def _lang(lang: str) -> str:
    return lang if lang in LANGS else "en"


def month_name(d, lang: str, today: date = None) -> str:
    today = today or date.today()
    name = MONTHS[_lang(lang)][d.month - 1]
    return name if d.year == today.year else f"{name} {d.year}"


def phrase(key: str, lang: str, month=None, code: str = None, today: date = None) -> str:
    """Frase lista para escribir. month: datetime/date del mes al que se refiere."""
    today = today or date.today()
    month = month or today
    prev = month.replace(day=1) - timedelta(days=1)
    return PHRASES[key][_lang(lang)].format(
        month=month_name(month, lang, today), prev=month_name(prev, lang, today),
        code=code or "OF0104")


def phrases(state: State, lang: str, today: date = None) -> List[str]:
    """Todas las frases útiles, las del siguiente paso primero."""
    today = today or date.today()
    last_month = today.replace(day=1) - timedelta(days=1)
    m = state.start
    P = lambda key, month=m: phrase(key, lang, month, state.top_code, today)  # noqa: E731

    stage = state.stage
    if stage == "start":
        keys = [("read", last_month), ("read", today), ("status", None)]
        keys += [("load_history", None), ("averages", None)] if state.has_history else [("load_history", None)]
    elif stage == "prorate":
        keys = [("prorate", m), ("summary", m), ("alerts", m), ("compare", m)]
    elif stage == "workday":
        keys = [("workday" if state.is_month else "workday_period", m), ("n4w", m), ("close", m),
                ("edit", None)]
        keys += [("why_prorate", None)] if state.prorated else []
    else:   # done
        keys = [("n4w", m), ("close", m), ("status", None), ("compare", m), ("read", today)]

    keys += [("read", last_month), ("read", today), ("status", None), ("week_hours", None),
             ("close", m or last_month), ("summary", m or last_month),
             ("compare", m or last_month), ("alerts", m or last_month),
             ("averages", None), ("project_avg", None), ("target", None), ("chart", None),
             ("load_history", None), ("my_projects", None), ("add_project", None),
             ("remove_project", None), ("import_excel", None), ("update_db", None),
             ("sync", None), ("help", None)]
    out = []
    for key, month in keys:
        text = P(key, month)
        if text not in out:
            out.append(text)
    return out


def progress(state: State) -> str:
    """Indicador textual de pasos para el encabezado."""
    if state.start is None:
        return "① Read ○  →  ② Prorate ○  →  ③ Workday ○   ·   ④ N4W ○"
    period = f"{state.start:%Y-%m}" if state.is_month else f"from {state.start:%Y-%m-%d}"
    if state.virtual:
        prorate = "② Prorate ✓" if state.prorated else "② Prorate ●"
    else:
        prorate = "② Prorate –"
    if state.workday_done:
        workday = "③ Workday ✓"
    elif not state.virtual or state.prorated:
        workday = "③ Workday ●"
    else:
        workday = "③ Workday ○"
    # N4W no depende del prorrateo ni de Workday (horas sin prorratear, semanas lun–dom)
    n4w = "④ N4W ✓" if state.n4w_done else "④ N4W ●"
    return f"① Read ✓  →  {prorate}  →  {workday}   ·   {n4w}   ·   {period}"


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def match(text: str, pool: List[str], limit: int = 5) -> List[str]:
    """Frases que contienen todas las palabras escritas (sin tildes ni mayúsculas)."""
    words = _norm(text).split()
    if not words:
        return []
    hits = [p for p in pool if all(w in _norm(p) for w in words) and _norm(p) != _norm(text).strip()]
    return hits[:limit]
