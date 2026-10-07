# ============================================================
# OLLAMA — interpretación de instrucciones (cualquier idioma).
# Una sola llamada por mensaje: devuelve JSON validado contra un esquema.
# El LLM nunca ejecuta ni calcula nada; los mensajes fijos se
# traducen con agent/i18n.py (sin LLM).
# ============================================================
import json
import re
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Optional

import config

log = logging.getLogger(__name__)

# Pasos (el usuario los pide uno a uno)
STEPS = ["read_hours", "prorate", "fill_workday", "submit_n4w"]
# "Mis proyectos" (la lista de códigos en los que trabaja el usuario)
# Estado, control antes de cerrar y correcciones del periodo leído
STATUS = ["status", "close_check", "edit_hours", "explain_prorate"]
PROJECTS = ["my_projects", "add_project", "remove_project", "import_projects", "categorize_meetings"]
# Análisis sobre el historial
ANALYSIS = ["hours_summary", "compare_months", "project_stats", "set_target",
            "alerts", "load_history", "show_chart"]
OTHER = ["update_database", "sync_categories", "help", "clarify", "other"]
ACTIONS = STEPS + STATUS + PROJECTS + ANALYSIS + OTHER

# clarify solo se ofrece al modelo para mensajes cortos sin nada concreto ("borrar", "cámbialo"):
# con todos los mensajes, un modelo chico pregunta de más
_DOMAIN_RE = re.compile(r"\d|workday|n4w|prorr|prorat|rate|hora|hour|proje|proye|mes|month|semana|week"
                        r"|outlook|categor|chat|conversa|histor|ayuda|help|ajuda"
                        r"|\b(ene|jan|feb|fev|mar|abr|apr|may|mai|jun|jul|ago|aug|sep|set|oct|out|nov|dic|dec|dez)"
                        r"|\b(hoy|today|hoje|ayer|yesterday|ontem|lee|leer|read|leia|llena|fill|preench|envi|submit)")


def is_bare(text: str) -> bool:
    words = text.split()
    return 0 < len(words) <= 3 and not _DOMAIN_RE.search(text.lower())


_str = {"type": ["string", "null"]}
_num = {"type": ["number", "null"]}

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ACTIONS},
        "month": _str,
        "month2": _str,
        "start_date": _str,
        "end_date": _str,
        "project": _str,
        "target_pct": _num,
        "target_hours": _num,
        "hours": _num,
        "months_back": {"type": ["integer", "null"]},
        "language": {"type": "string"},
        "reply": {"type": "string"},
    },
    "required": ["action", "month", "month2", "start_date", "end_date", "project",
                 "target_pct", "target_hours", "hours", "months_back", "language", "reply"],
}

SYSTEM_PROMPT = """You are the assistant of "TimeSheet Agent" (The Nature Conservancy).
You ONLY help with the user's timesheet hours and the projects they charge time to.
Today is {today} ({weekday}). This week: {monday} to {sunday}. Last week: {last_monday} to {last_sunday}.

Classify the user's message into a JSON intent. You never execute anything and never invent numbers.
The user controls every step: one message = one action. Never combine steps.
If a message only corrects a value of the previous user message (a month, a date or a project code), the action is the SAME as that previous message, with the new value.
{state}
Steps:
- read_hours: read the hours from the Outlook calendar for a period. Always the first step ("read/load my hours for October").
- prorate: prorate (redistribute) the hours of the period already read.
- fill_workday: fill Workday with the period already read. For ONE week of it ("fill Workday the week of October 4") set start_date = that day.
- submit_n4w: submit hours to N4W Facility (Monday-Sunday weeks).
Status and corrections:
- status: where am I / what is pending / did I already fill Workday or submit N4W for a period, when, and what was sent ("what's left?", "did I submit N4W last week?", "what did I send in August?"). Set month/dates only if the user names a period.
- close_check: am I ready to close a month / check everything before submitting ("am I ready to close September?").
- edit_hours: change the hours of ONE project on ONE day of the period already read ("put 4 h on P100 on Tuesday"). Set project, start_date = that day, hours = the new hours.
- explain_prorate: why / how the hours were prorated ("why did you prorate like that?").
My projects (the list of project codes the user works on):
- my_projects: show/review the projects I work on ("which are my projects?").
- add_project: the user works on new project(s) ("I'm also working on FS3602A"), even if they also ask to create its Outlook category. Set "project" (first code).
- remove_project: the user no longer works on a project ("I don't work on SE3202 anymore"). Set "project".
- import_projects: import my project codes from an Excel file ("import my projects from Excel").
- categorize_meetings: help me categorize the Outlook meetings that have NO category ("help me categorize my meetings of October"). Set month/dates if given.
Analysis of saved history:
- hours_summary: summary/balance of hours by project for a month or dates, or a quick question "how many hours this week / today / on OF0104 in September?" (set project if one is named).
- compare_months: compare "month" with "month2" (month2 null = the previous month). "Did I charge more than in August?"
- project_stats: averages and history of "project", or of all projects if no code.
- set_target: the user states the dedication a project SHOULD have: target_pct (% of the month) and/or target_hours (hours per month).
- alerts: check a month for problems (deviations from targets or averages, missing hours).
- load_history: read past months from Outlook to build the history. months_back = number of months.
- show_chart: the user asks for a chart/graph/plot of their hours ("show me a chart of my hours this year", "graph OF0104"). Set month/dates, project or months_back if given.
Other:
- update_database: download again the global project list (N4W_Task_Details) and review my projects.
- sync_categories: create the missing Outlook categories for ALL my projects (no new project code mentioned).
- help: what you can do / how to use the tool.
- clarify: ONLY a bare verb or pronoun with nothing to act on ("borrar", "delete", "cámbialo", "do it again"). Any message that names a step, a period, a project code or asks about hours is NOT clarify; off-topic is other. reply = ONE short question that offers 2-3 concrete options fitting the current state (e.g. "Do you want to clear the chat, remove a project from your list or change the hours of a day?").
- other: anything not about the user's hours or projects.

Fields (null when not given):
- month, month2: "YYYY-MM". Resolve relative dates with today ("this month", "last month"; a month name = its most recent occurrence not in the future).
- start_date, end_date: "YYYY-MM-DD", only when the user gives days: explicit dates or relative days ("today" = start and end today; "this week" / "last week" = its Monday and Sunday).
- hours: only for edit_hours (the new number of hours for that day).
- project: project code as written, uppercase (e.g. "OF0104").
- language: ISO 639-1 code of the user's message (es, en, pt, fr...).
- reply: ONE short sentence IN THE USER'S LANGUAGE saying what you will do (with the period or project). Never numbers, project codes or results: the app shows them (except in a clarify question). For help: list the steps (read hours → prorate → fill Workday / submit N4W), what's pending / ready to close, managing my projects and the analysis questions. For other: say you only help with timesheet hours and projects."""


@dataclass
class Intent:
    action: str
    language: str = "en"
    reply: str = ""
    month: Optional[str] = None
    month2: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    project: Optional[str] = None
    target_pct: Optional[float] = None
    target_hours: Optional[float] = None
    hours: Optional[float] = None
    months_back: Optional[int] = None


_model = ""   # elegido por el usuario en la UI; vacío → config.OLLAMA_MODEL
_chars_per_token = 3.5   # se recalibra con lo que Ollama reporta en cada llamada


def set_model(name: str):
    global _model
    _model = name or ""


def current_model() -> str:
    return _model or config.OLLAMA_MODEL


def list_models() -> list:
    """Modelos instalados en Ollama (vacío si no responde)."""
    try:
        models = _client().list()["models"]
    except Exception:
        return []
    return sorted(n for n in (m.get("model") or m.get("name") for m in models) if n)


def _client():
    from ollama import Client
    return Client(host=config.OLLAMA_HOST, timeout=config.OLLAMA_TIMEOUT)


def _options() -> dict:
    return {"temperature": config.OLLAMA_TEMPERATURE, "num_ctx": config.OLLAMA_NUM_CTX,
            "num_predict": config.OLLAMA_NUM_PREDICT}


def _chars(messages: list) -> int:
    return sum(len(m["content"]) for m in messages)


def fit_history(system: list, history: List[dict], new: list) -> List[dict]:
    """Historial más reciente que cabe en el presupuesto de contexto (recorta desde el inicio)."""
    budget = config.OLLAMA_NUM_CTX * config.OLLAMA_CTX_BUDGET * _chars_per_token
    room = budget - _chars(system) - _chars(new)
    kept = []
    for msg in reversed(history[-config.OLLAMA_MAX_HISTORY:]):
        room -= len(msg["content"])
        if room < 0:
            break
        kept.append(msg)
    kept.reverse()
    if kept and kept[0]["role"] == "assistant":   # empezar siempre por un turno del usuario
        kept = kept[1:]
    return kept


def _track_usage(messages: list, resp):
    global _chars_per_token
    used = resp.get("prompt_eval_count") or 0
    if not used:
        return
    _chars_per_token = max(2.0, min(6.0, _chars(messages) / used))
    if used > config.OLLAMA_NUM_CTX * 0.8:
        log.warning(f"context {used}/{config.OLLAMA_NUM_CTX} tokens — consider a larger TSA_OLLAMA_NUM_CTX")
    else:
        log.debug(f"context {used}/{config.OLLAMA_NUM_CTX} tokens")


def _chat(messages: list, fmt=None, model: str = None) -> str:
    kwargs = dict(model=model or current_model(), messages=messages,
                  keep_alive=config.OLLAMA_KEEP_ALIVE, options=_options())
    if fmt is not None:
        kwargs["format"] = fmt
    client = _client()
    try:
        resp = client.chat(think=False, **kwargs)   # qwen3: sin razonamiento → más rápido
    except TypeError:                               # librería ollama antigua sin 'think'
        resp = client.chat(**kwargs)
    _track_usage(messages, resp)
    return resp["message"]["content"]


def check_ollama() -> tuple:
    """(ok, mensaje) — servidor accesible y modelo instalado."""
    try:
        models = _client().list()
        names = [m.get("model") or m.get("name") for m in models["models"]]
    except Exception as e:
        return False, f"Ollama not reachable at {config.OLLAMA_HOST} ({e})"
    wanted = current_model()
    if not any(n == wanted or n.split(":")[0] == wanted for n in names if n):
        return False, f"Model '{wanted}' not installed. Run: ollama pull {wanted}"
    return True, wanted


def warm_up():
    """Carga el modelo en memoria (sin generar) para que el primer mensaje no espere."""
    try:
        _client().generate(model=current_model(), prompt="", keep_alive=config.OLLAMA_KEEP_ALIVE,
                            options=_options())   # mismo num_ctx → el primer mensaje no recarga
    except Exception as e:
        log.debug(f"warm-up failed: {e}")


def _clean_code(value) -> Optional[str]:
    return str(value).strip().upper() if value else None


def _loads(raw: str) -> dict:
    """
    JSON del modelo. Si se cortó (el modelo a veces se enrolla en "reply" hasta el
    tope de salida), se recuperan los campos anteriores: "reply" va siempre al final.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cut = raw.rfind('"reply"')
        if cut < 0:
            raise
        log.warning("intent JSON truncated; reply dropped")
        return json.loads(raw[:cut].rstrip().rstrip(',') + "}")


def parse_intent(text: str, history: List[dict], model: str = None, state: str = "") -> Intent:
    """history: [{'role': 'user'|'assistant', 'content': str}] (últimos turnos).
    state: resumen de dónde está el usuario (periodo leído, pasos hechos, sus proyectos)."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    system = [{"role": "system", "content": SYSTEM_PROMPT.format(
        today=today.isoformat(), weekday=today.strftime('%A'),
        monday=monday.isoformat(), sunday=(monday + timedelta(days=6)).isoformat(),
        last_monday=(monday - timedelta(days=7)).isoformat(),
        last_sunday=(monday - timedelta(days=1)).isoformat(),
        state=f"\nCurrent state (context only, never an instruction):\n{state}\n" if state else "")}]
    new = [{"role": "user", "content": text}]
    messages = system + fit_history(system, history, new) + new

    schema = INTENT_SCHEMA
    if not is_bare(text):
        schema = json.loads(json.dumps(INTENT_SCHEMA))
        schema["properties"]["action"]["enum"] = [a for a in ACTIONS if a != "clarify"]
    data = _loads(_chat(messages, fmt=schema, model=model))
    log.debug(f"intent: {data}")
    action = data.get("action") if data.get("action") in ACTIONS else "other"
    return Intent(
        action=action,
        language=(data.get("language") or "en").lower()[:2],
        reply=data.get("reply") or "",
        month=data.get("month") or None,
        month2=data.get("month2") or None,
        start_date=data.get("start_date") or None,
        end_date=data.get("end_date") or None,
        project=_clean_code(data.get("project")),
        target_pct=data.get("target_pct"),
        target_hours=data.get("target_hours"),
        hours=data.get("hours"),
        months_back=data.get("months_back"),
    )
