# ============================================================
# AGENTE — conecta el chat con los flujos deterministas.
#   mensaje → [LLM] intención → validación en Python → workflow
# Las decisiones/aprobaciones del pipeline llegan a la UI traducidas
# al idioma del usuario. Los textos fijos de la UI están en inglés.
# ============================================================
import traceback
from datetime import datetime
from typing import List, Protocol

import workflows
from agent import llm
from agent.settings import Settings
from core import timesheet
from pipeline import Callbacks, Cancelled, Decision, Pipeline


class AgentUI(Protocol):
    def say(self, text: str): ...
    def log(self, text: str): ...
    def decide(self, decision: Decision): ...           # bloqueante
    def approve(self, title: str, detail: str) -> bool: ...   # bloqueante


class NeedInfo(Exception):
    """Falta un dato que el usuario debe dar (no es un error)."""


class Agent:
    def __init__(self, ui: AgentUI, settings: Settings):
        self.ui = ui
        self.settings = settings
        self.lang = "en"
        self.history: List[dict] = []

    # ── utilidades ───────────────────────────────────────────
    def t(self, text: str) -> str:
        return llm.localize(text, self.lang)

    def _pipeline(self) -> Pipeline:
        def decide(d: Decision):
            d.question = self.t(d.question)
            return self.ui.decide(d)

        def approve(title: str, detail: str) -> bool:
            return self.ui.approve(self.t(title), detail)

        cb = Callbacks(log=self.ui.log, decide=decide, approve=approve)
        return Pipeline(self.settings.db_path, email=self.settings.email, callbacks=cb)

    def _remember(self, role: str, content: str):
        self.history.append({"role": role, "content": content})
        self.history = self.history[-12:]

    # ── entrada principal (se llama desde un hilo de trabajo) ─
    def handle(self, text: str):
        try:
            intent = llm.parse_intent(text, self.history)
        except Exception as e:
            self.ui.log(traceback.format_exc())
            self.ui.say(f"⚠ Could not reach the language model: {e}")
            return

        self.lang = intent.language
        self._remember("user", text)
        if intent.reply:
            self.ui.say(intent.reply)
            self._remember("assistant", intent.reply)
        self.ui.log(f"[intent] {intent}")

        if intent.action in ("help", "other"):
            return

        missing = self.settings.missing(need_email=intent.action == "submit_n4w")
        if missing:
            self.ui.say(self.t(f"Please set {', '.join(missing)} in Settings (⚙) first."))
            return

        try:
            done = self._dispatch(intent)
            if done:
                self.ui.say(self.t(done))
        except NeedInfo as e:
            self.ui.say(self.t(str(e)))
        except Cancelled:
            self.ui.say(self.t("Cancelled. Nothing else was changed."))
        except Exception as e:
            self.ui.log(traceback.format_exc())
            self.ui.say(self.t(f"⚠ Error: {e}"))

    # ── despacho determinista ────────────────────────────────
    def _month(self, intent) -> tuple:
        if not intent.month:
            raise NeedInfo("Which month? (e.g. October 2026)")
        return workflows.parse_month(intent.month)

    def _dispatch(self, intent) -> str:
        pipe = self._pipeline()
        a = intent.action

        if a == "update_database":
            removed = pipe.update_database()
            return f"✓ Database updated ({len(removed)} closed projects removed)."

        if a == "sync_categories":
            pipe.sync_categories()
            return "✓ Outlook categories synced."

        if a == "fill_workday":
            y, m = self._month(intent)
            workflows.run_workday_month(pipe, y, m, use_prorate=intent.prorate)
            return f"✓ Workday filled for {datetime(y, m, 1):%B %Y}."

        if a == "submit_n4w":
            if intent.start_date and intent.end_date:
                start, end = workflows.parse_weeks(intent.start_date, intent.end_date)
            else:
                start, end = workflows.choose_n4w_weeks(pipe, *self._month(intent))
            dst = workflows.run_n4w(pipe, start, end)
            return f"✓ N4W submitted ({start:%Y-%m-%d} → {end:%Y-%m-%d}): {dst}"

        if a == "report":
            if intent.start_date and intent.end_date:
                start = datetime.strptime(intent.start_date, '%Y-%m-%d')
                end = datetime.strptime(intent.end_date, '%Y-%m-%d')
            else:
                start, end = timesheet.month_bounds(*self._month(intent))
            findings = workflows.run_report(pipe, start, end)
            return f"✓ Report saved: {findings['path']}"

        return ""
