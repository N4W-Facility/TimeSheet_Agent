# ============================================================
# OLLAMA — interpretación de instrucciones (cualquier idioma)
# y traducción de mensajes al idioma del usuario.
# El LLM nunca ejecuta nada: devuelve JSON validado contra un esquema.
# ============================================================
import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

import config

log = logging.getLogger(__name__)

ACTIONS = ["fill_workday", "submit_n4w", "report", "update_database",
           "sync_categories", "help", "other"]

INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ACTIONS},
        "month": {"type": ["string", "null"], "description": "YYYY-MM"},
        "start_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
        "end_date": {"type": ["string", "null"], "description": "YYYY-MM-DD"},
        "prorate": {"type": "boolean"},
        "language": {"type": "string", "description": "ISO 639-1 code of the user's message"},
        "reply": {"type": "string"},
    },
    "required": ["action", "month", "start_date", "end_date", "prorate", "language", "reply"],
}

SYSTEM_PROMPT = """You are the assistant of "TimeSheet Agent", a tool that fills employee timesheets for The Nature Conservancy.
Today is {today} ({weekday}).

Your ONLY job is to classify the user's message into a JSON intent. You never execute anything yourself.

Actions:
- fill_workday: fill Workday with hours from the Outlook calendar. Workday is always a calendar MONTH → set "month".
- submit_n4w: submit hours to N4W Facility. N4W uses complete Monday–Sunday weeks. If the user gives dates, set start_date/end_date; if they only name a month, set "month".
- report: only generate/preview the hours for a period (nothing is submitted). Set "month" or start_date/end_date.
- update_database: refresh the project codes database from Box.
- sync_categories: create/remove Outlook categories from the database.
- help: the user asks what you can do or how to use the tool.
- other: greetings, unrelated or unclear requests.

Rules:
- Resolve relative dates using today ("this month", "last month", "octubre" = the most recent October that is not in the future unless the user says otherwise).
- "prorate" is true only if the user explicitly asks to prorate/redistribute hours.
- "language": ISO 639-1 code of the language the user wrote in (es, en, pt, fr, ...).
- "reply": one or two short sentences IN THE USER'S LANGUAGE. For actions, restate what will be done including the period. For help, briefly list what you can do. For other, answer briefly and steer back to timesheets. If the period is missing for an action that needs it, ask for it.
- Never invent hours, project codes or results."""


@dataclass
class Intent:
    action: str
    month: Optional[str]
    start_date: Optional[str]
    end_date: Optional[str]
    prorate: bool
    language: str
    reply: str


def _client():
    from ollama import Client
    return Client(host=config.OLLAMA_HOST)


def _chat(messages: list, fmt=None) -> str:
    kwargs = dict(model=config.OLLAMA_MODEL, messages=messages,
                  options={"temperature": 0, "num_ctx": config.OLLAMA_NUM_CTX})
    if fmt is not None:
        kwargs["format"] = fmt
    client = _client()
    try:
        resp = client.chat(think=False, **kwargs)   # qwen3: sin razonamiento → más rápido
    except TypeError:                               # librería ollama antigua sin 'think'
        resp = client.chat(**kwargs)
    return resp["message"]["content"]


def check_ollama() -> tuple:
    """(ok, mensaje) — servidor accesible y modelo instalado."""
    try:
        models = _client().list()
        names = [m.get("model") or m.get("name") for m in models["models"]]
    except Exception as e:
        return False, f"Ollama not reachable at {config.OLLAMA_HOST} ({e})"
    wanted = config.OLLAMA_MODEL
    if not any(n == wanted or n.split(":")[0] == wanted for n in names if n):
        return False, f"Model '{wanted}' not installed. Run: ollama pull {wanted}"
    return True, wanted


def parse_intent(text: str, history: List[dict]) -> Intent:
    """history: [{'role': 'user'|'assistant', 'content': str}] (últimos turnos)."""
    today = date.today()
    messages = [{"role": "system",
                 "content": SYSTEM_PROMPT.format(today=today.isoformat(), weekday=today.strftime('%A'))}]
    messages += history[-6:]
    messages.append({"role": "user", "content": text})

    raw = _chat(messages, fmt=INTENT_SCHEMA)
    data = json.loads(raw)
    log.debug(f"intent: {data}")
    action = data.get("action") if data.get("action") in ACTIONS else "other"
    return Intent(
        action=action,
        month=data.get("month") or None,
        start_date=data.get("start_date") or None,
        end_date=data.get("end_date") or None,
        prorate=bool(data.get("prorate")),
        language=(data.get("language") or "en").lower()[:2],
        reply=data.get("reply") or "",
    )


_cache = {}


def localize(text: str, lang: str) -> str:
    """Traduce un mensaje del sistema (en inglés) al idioma del usuario."""
    if not text or lang == "en":
        return text
    key = (text, lang)
    if key not in _cache:
        try:
            _cache[key] = _chat([
                {"role": "system", "content":
                    f"Translate the user's text into the language with ISO code '{lang}'. "
                    "Keep numbers, dates, project codes, file names and symbols (✓ ⚠ →) unchanged. "
                    "Output only the translation."},
                {"role": "user", "content": text},
            ]).strip()
        except Exception as e:
            log.warning(f"Translation failed: {e}")
            return text
    return _cache[key]
