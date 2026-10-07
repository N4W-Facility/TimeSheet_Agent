# ============================================================
# OLLAMA — interpretación de instrucciones (cualquier idioma).
# Una sola llamada por mensaje: devuelve JSON validado contra un esquema.
# El LLM nunca ejecuta ni calcula nada; los mensajes fijos se
# traducen con agent/i18n.py (sin LLM).
# ============================================================
import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

import config

log = logging.getLogger(__name__)

# Pasos (el usuario los pide uno a uno)
STEPS = ["read_hours", "prorate", "fill_workday", "submit_n4w"]
# "Mis proyectos" (la lista de códigos en los que trabaja el usuario)
PROJECTS = ["my_projects", "add_project", "remove_project", "import_projects", "categorize_meetings"]
# Análisis sobre el historial
ANALYSIS = ["hours_summary", "compare_months", "project_stats", "set_target",
            "alerts", "load_history", "show_chart"]
OTHER = ["update_database", "sync_categories", "help", "other"]
ACTIONS = STEPS + PROJECTS + ANALYSIS + OTHER

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
        "months_back": {"type": ["integer", "null"]},
        "language": {"type": "string"},
        "reply": {"type": "string"},
    },
    "required": ["action", "month", "month2", "start_date", "end_date", "project",
                 "target_pct", "target_hours", "months_back", "language", "reply"],
}

SYSTEM_PROMPT = """You are the assistant of "TimeSheet Agent" (The Nature Conservancy).
You ONLY help with the user's timesheet hours and the projects they charge time to.
Today is {today} ({weekday}).

Classify the user's message into a JSON intent. You never execute anything and never invent numbers.
The user controls every step: one message = one action. Never combine steps.

Steps:
- read_hours: read the hours from the Outlook calendar for a period. Always the first step ("read/load my hours for October").
- prorate: prorate (redistribute) the hours of the period already read.
- fill_workday: fill Workday with the month already read. For ONE week of it ("fill Workday the week of October 4") set start_date = that day.
- submit_n4w: submit hours to N4W Facility (Monday-Sunday weeks).
My projects (the list of project codes the user works on):
- my_projects: show/review the projects I work on ("which are my projects?").
- add_project: the user works on new project(s) ("I'm also working on FS3602A"), even if they also ask to create its Outlook category. Set "project" (first code).
- remove_project: the user no longer works on a project ("I don't work on SE3202 anymore"). Set "project".
- import_projects: import my project codes from an Excel file ("import my projects from Excel").
- categorize_meetings: help me categorize the Outlook meetings that have NO category ("help me categorize my meetings of October"). Set month/dates if given.
Analysis of saved history:
- hours_summary: summary/balance of hours by project for a month or dates.
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
- other: anything not about the user's hours or projects.

Fields (null when not given):
- month, month2: "YYYY-MM". Resolve relative dates with today ("this month", "last month"; a month name = its most recent occurrence not in the future).
- start_date, end_date: "YYYY-MM-DD", only when the user gives explicit days.
- project: project code as written, uppercase (e.g. "OF0104").
- language: ISO 639-1 code of the user's message (es, en, pt, fr...).
- reply: ONE short sentence IN THE USER'S LANGUAGE saying what you will do (with the period or project). Never numbers or results: the app shows them. For help: list the steps (read hours → prorate → fill Workday / submit N4W), managing my projects and the analysis questions. For other: say you only help with timesheet hours and projects."""


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
    return {"temperature": 0, "num_ctx": config.OLLAMA_NUM_CTX,
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


def parse_intent(text: str, history: List[dict], model: str = None) -> Intent:
    """history: [{'role': 'user'|'assistant', 'content': str}] (últimos turnos)."""
    today = date.today()
    system = [{"role": "system",
               "content": SYSTEM_PROMPT.format(today=today.isoformat(), weekday=today.strftime('%A'))}]
    new = [{"role": "user", "content": text}]
    messages = system + fit_history(system, history, new) + new

    data = json.loads(_chat(messages, fmt=INTENT_SCHEMA, model=model))
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
        months_back=data.get("months_back"),
    )
