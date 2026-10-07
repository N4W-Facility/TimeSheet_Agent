# ============================================================
# AGENTE — conecta el chat con pasos deterministas.
#   mensaje → [LLM] intención → validación en Python → UN paso
# El usuario controla el flujo: cada paso se pide por separado
# (leer → prorratear → Workday / N4W) y el agente exige el orden.
# Los números salen de core/analysis.py; el historial (core/history.py)
# acumula los meses para comparar, promediar y alertar.
# ============================================================
import os
import re
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional, Protocol

import pandas as pd

import config
import workflows
from agent import i18n, llm, suggest
from agent.settings import Settings
from core import analysis, categorize, charts, database, holidays_cal, n4w, timesheet
from core.history import History
from core.utils import get_date_columns
from pipeline import Callbacks, Cancelled, Decision, Pipeline


class AgentUI(Protocol):
    def say(self, text: str): ...
    def log(self, text: str): ...
    def show(self, title: str, detail: str): ...                # tarjeta informativa
    def decide(self, decision: Decision): ...                   # bloqueante
    def approve(self, title: str, detail: str) -> bool: ...     # bloqueante
    def confirm_send(self, title: str, detail: str, warning: str,
                     ok: str, cancel: str) -> bool: ...         # bloqueante; acción irreversible
    def pick_file(self, title: str) -> Optional[str]: ...       # explorador de archivos (bloqueante)
    def chart(self, spec: dict): ...                            # tarjeta con gráfica (core.charts)


class NeedInfo(Exception):
    """Falta un dato o un paso previo (no es un error). El mensaje ya va traducido."""


def period_label(start: datetime, end: datetime) -> str:
    if (start, end) == timesheet.month_bounds(start.year, start.month):
        return f"{start:%Y-%m}"
    return f"{start:%Y-%m-%d} → {end:%Y-%m-%d}"


@dataclass
class Loaded:
    """Periodo leído de Outlook en esta sesión (base de los pasos siguientes)."""
    start: datetime
    end: datetime
    path: str
    is_month: bool
    virtual: List[str] = field(default_factory=list)
    prorated_path: Optional[str] = None
    workday_done: bool = False

    @property
    def label(self) -> str:
        return period_label(self.start, self.end)


# Acciones que necesitan que el usuario haya armado "mis proyectos"
NEEDS_PROJECTS = {"read_hours", "prorate", "fill_workday", "submit_n4w", "load_history",
                  "categorize_meetings"}

# Respuestas cortas a "¿cuál debería ser tu dedicación a X?" (se interpretan sin LLM)
SAME_WORDS = {"same", "keep", "ok", "yes", "igual", "si", "asi", "mantener", "mesmo", "sim", "manter"}
SKIP_WORDS = {"skip", "next", "no", "omitir", "saltar", "siguiente", "pasar", "pular", "nao", "proximo"}
STOP_WORDS = {"stop", "later", "cancel", "parar", "despues", "luego", "cancelar", "depois", "mais tarde"}
ANSWER_WORDS = {"en": ("same", "skip"), "es": ("igual", "omitir"), "pt": ("mesmo", "pular")}
# "importar mi Excel" → explorador de archivos (sin LLM)
IMPORT_RE = re.compile(r"\b(import\w*|excel|xlsx)\b")
# Saludo a secas → estado del periodo (sin LLM: el modelo pequeño lo confunde con otros pasos)
GREETINGS = {"hola": "es", "buenas": "es", "buenos dias": "es", "buenas tardes": "es",
             "hi": "en", "hello": "en", "hey": "en", "good morning": "en",
             "oi": "pt", "ola": "pt", "bom dia": "pt", "boa tarde": "pt"}
# "¿Qué puedes hacer?" → tarjeta de ayuda (sin LLM: respuesta inmediata y siempre igual)
HELP_RE = re.compile(
    r"^(help|ayuda|ajuda)$"
    r"|what (else )?can you do|how can you help|what do you do"
    r"|que (mas )?(puedes|sabes) hacer|en que (me )?(puedes |podes )?ayudar|en que me ayudas"
    r"|como (me )?puedes ayudar"
    r"|o que (mais )?(voce )?(pode|sabe) fazer|em que (voce )?(pode )?me ajudar|como (voce )?pode me ajudar")
TARGET_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(%|h|hs|hrs|hours|horas|horas/mes)?")


class Agent:
    def __init__(self, ui: AgentUI, settings: Settings, store: History = None):
        self.ui = ui
        self.settings = settings
        self.lang = settings.language or "en"    # último idioma usado (persistido)
        self.chat_history: List[dict] = []
        self._store = store
        self.loaded: Optional[Loaded] = None
        self.global_checked = False                 # base global descargada en esta sesión
        self.status: dict = {}                      # código → estado en N4W_Task_Details
        self.pending_targets: List[dict] = []       # dedicaciones por preguntar
        self.awaiting_codes = False                 # se preguntó "¿en qué proyectos trabajas?"
        self.text = ""                              # último mensaje (para extraer códigos)

    # ── utilidades ───────────────────────────────────────────
    @property
    def store(self) -> History:
        if self._store is None:
            self._store = History(config.HISTORY_DB)
        return self._store

    def m(self, key: str, **kw) -> str:
        return i18n.tr(key, self.lang, **kw)

    def p(self, key: str, month=None, code: str = None) -> str:
        """Frase sugerida en el idioma del usuario (ver agent/suggest.py)."""
        return suggest.phrase(key, self.lang, month, code or self._top_code())

    @staticmethod
    def _last_month() -> datetime:
        return datetime.now().replace(day=1) - timedelta(days=1)

    # ── estado para sugerencias y progreso (lo consulta la UI) ─
    def _top_code(self) -> Optional[str]:
        if not self.loaded:
            return None
        table = analysis.by_project(self.store.hours(self.loaded.start, self.loaded.end))
        return table.index[0] if len(table) else None

    def state(self) -> suggest.State:
        L = self.loaded
        if not L:
            return suggest.State(has_history=bool(self.store.months()))
        return suggest.State(start=L.start, is_month=L.is_month, virtual=tuple(L.virtual),
                             prorated=bool(L.prorated_path), workday_done=L.workday_done,
                             n4w_done=self._n4w_done(L), has_history=True, top_code=self._top_code())

    def _n4w_done(self, L: Loaded) -> bool:
        """Hay un envío N4W registrado que toca el periodo leído."""
        try:
            return bool((self.store.events(L.start, L.end)['step'] == 'n4w').any())
        except Exception:
            return False

    def suggestions(self) -> List[str]:
        tips = suggest.phrases(self.state(), self.lang)
        if self.pending_targets:                    # respuesta a la pregunta de dedicación
            same, skip = ANSWER_WORDS.get(self.lang, ANSWER_WORDS["en"])
            tips = [same, skip] + tips
        elif self.awaiting_codes:                   # "¿en qué proyectos trabajas?"
            tips = [self.p("import_excel")] + tips
        return tips

    def progress(self) -> str:
        return suggest.progress(self.state())

    def _pipeline(self) -> Pipeline:
        cb = Callbacks(log=self.ui.log, decide=self.ui.decide, approve=self.ui.approve)
        return Pipeline(email=self.settings.email, callbacks=cb, country=self._country())

    def _country(self) -> str:
        """País para los festivos: settings.json o, la primera vez, la región de Windows."""
        if not self.settings.country:
            self.settings.country = holidays_cal.detect_country()
            if self.settings.country:
                self.ui.log(f"Country (Windows region): {self.settings.country}")
                try:
                    self.settings.save()
                except OSError:
                    pass
        return self.settings.country

    def _ensure_global(self):
        """Base global descargada una vez por sesión (antes de leer Outlook)."""
        if not self.global_checked:
            self.check_global()
        if not self.status:
            self.status = self._pipeline().task_status()

    def _remember(self, role: str, content: str):
        self.chat_history.append({"role": role, "content": content})
        self.chat_history = self.chat_history[-100:]   # llm.fit_history recorta según el contexto

    # ── entrada principal (se llama desde un hilo de trabajo) ─
    def handle(self, text: str):
        if self.pending_targets and self._answer_target(text):
            return
        if self.awaiting_codes and self._answer_codes(text):
            return
        self.text = text
        greeting = GREETINGS.get(suggest._norm(text).strip(" !.¡,"))
        if greeting:
            self._greeting(text, greeting)
            return
        help_lang = self._help_lang(text)
        if help_lang:
            self._set_lang(help_lang)
            self._remember("user", text)
            self.do_help()
            return
        try:
            intent = llm.parse_intent(text, self.chat_history)
        except Exception as e:
            self.ui.log(traceback.format_exc())
            self.ui.say(self.m("llm_down", err=e))
            return

        self._set_lang(intent.language)
        self._remember("user", text)
        if intent.reply and intent.action != "help":
            self.ui.say(intent.reply)
            self._remember("assistant", intent.reply)
        self.ui.log(f"[intent] {intent}")

        if intent.action == "help":
            self.do_help()
            return
        if intent.action == "other":
            return
        if intent.action in NEEDS_PROJECTS and not self.store.projects_initialized():
            self._ask_projects()
            return
        if intent.action == "submit_n4w" and not self.settings.email:
            self.ui.say(self.m("need_email"))
            return

        try:
            getattr(self, f"do_{intent.action}")(intent)
        except NeedInfo as e:
            self.ui.say(str(e))
        except Cancelled:
            self.ui.say(self.m("cancelled"))
        except Exception as e:
            self.ui.log(traceback.format_exc())
            self.ui.say(self.m("error", err=e))

    def _set_lang(self, lang: Optional[str]):
        self.lang = lang or self.lang
        if self.lang != self.settings.language:      # el saludo y las sugerencias usan este idioma
            self.settings.language = self.lang
            try:
                self.settings.save()
            except OSError:
                pass

    def _greeting(self, text: str, lang: str):
        """"Hola" → dónde va el usuario (estado del periodo actual) y el siguiente paso."""
        self._set_lang(lang)
        self._remember("user", text)
        self.ui.say(self.m("hello"))
        try:
            self.do_status(llm.Intent(action="status", language=lang))
        except Exception as e:
            self.ui.log(traceback.format_exc())
            self.ui.say(self.m("error", err=e))

    @staticmethod
    def _help_lang(text: str) -> Optional[str]:
        """Idioma de una pregunta de ayuda ("¿qué puedes hacer?"), o None si no lo es."""
        norm = re.sub(r"[¿?¡!.,]", " ", suggest._norm(text))
        norm = " ".join(norm.split())
        if not HELP_RE.search(norm):
            return None
        if re.search(r"\b(voce|pode|fazer|ajuda|ajudar|o que|em que)\b", norm):
            return "pt"
        if re.search(r"\b(puedes|podes|sabes|hacer|ayuda|ayudar|ayudas|que)\b", norm):
            return "es"
        return "en"

    def do_help(self, intent=None):
        """Todo lo que el agente sabe hacer, con ejemplos listos para copiar en el idioma del usuario."""
        month = self.loaded.start if self.loaded else self._last_month()
        keys = ["read", "categorize", "edit", "prorate", "workday", "n4w", "status", "close",
                "week_hours", "summary", "compare", "alerts", "averages", "target", "chart",
                "my_projects", "add_project", "remove_project", "import_excel", "sync"]
        self.ui.show("What I can do", self.m("help_card", **{k: self.p(k, month).strip() for k in keys}))
        self.ui.say(self.m("help_short", next=self.suggestions()[0]))

    # ── al abrir la app ──────────────────────────────────────
    def greet(self):
        """Bienvenida + retomar el paso pendiente o sugerir cómo empezar."""
        self.ui.say(self.m("welcome"))
        self.start_hint()

    def start_hint(self):
        """
        Al abrir: base global → armar "mis proyectos" (primera vez) → revisarlos
        → retomar el paso pendiente o sugerir cómo empezar.
        """
        if not self.global_checked:
            self.check_global()
            self._ensure_absence_categories()
        if self.onboard():
            return
        self.review_projects()
        self._next_hint()

    def _next_hint(self):
        if not self.resume():
            tips = self.suggestions()
            self.ui.say(self.m("start_examples", a=tips[0], b=tips[1]))

    def check_global(self):
        """
        Descarga N4W_Task_Details (la base global: proyectos activos, cerrados,
        prorrateables). Sin red usa la copia local.
        """
        pipe = self._pipeline()
        try:
            fresh, at = pipe.refresh_task_details()
            self.status = pipe.task_status()
        except Exception as e:
            self.ui.log(traceback.format_exc())
            self.ui.say(self.m("global_failed", err=e))
            return
        self.global_checked = True
        active = sum(1 for v in self.status.values() if v['status'] == 'active')
        self.ui.say(self.m("global_ok" if fresh else "global_stale", at=at, n=active))

    # ── MIS PROYECTOS ────────────────────────────────────────
    def onboard(self) -> bool:
        """
        Primera vez: importa los códigos del Excel antiguo (si existe) o pregunta
        en qué proyectos trabaja. True si queda esperando la respuesta.
        """
        if self.store.projects_initialized() or not self.status:
            return False
        legacy = self.settings.legacy_db()
        if legacy and self._import_excel(legacy, quiet=True):
            return False
        self._ask_projects()
        return True

    def _ask_projects(self):
        self.awaiting_codes = True
        self.ui.say(self.m("ask_projects", phrase=self.p("import_excel")))

    def _import_excel(self, path: Optional[str] = None, quiet: bool = False) -> bool:
        """
        Importa los códigos de un Excel de proyectos antiguo (hoja N4W-Projects).
        Sin ruta abre el explorador. True si quedó al menos un proyecto en la lista.
        """
        if not path:
            path = self.ui.pick_file("Select your projects Excel")
            if not path:
                return False
        try:
            codes = database.legacy_codes(path)
        except Exception as e:
            self.ui.log(traceback.format_exc())
            if not quiet:
                self.ui.say(self.m("import_failed", file=os.path.basename(path), err=e))
            return False
        if not codes:
            if not quiet:
                self.ui.say(self.m("import_empty", file=os.path.basename(path)))
            return False
        if path != self.settings.db_path:            # recordar la ruta (no se vuelve a pedir)
            self.settings.db_path = path
            try:
                self.settings.save()
            except OSError:
                pass
        self.ui.say(self.m("import_legacy", n=len(codes)))
        before = len(self.store.my_projects())
        self._add_codes(codes)
        return len(self.store.my_projects()) > before

    def _answer_codes(self, text: str) -> bool:
        """Respuesta a "¿en qué proyectos trabajas?". False → no hay códigos: pasa al LLM."""
        try:
            self._ensure_global()
        except Exception as e:
            self.ui.say(self.m("global_failed", err=e))
            return True
        known, unknown = database.extract_codes(text, self.status)
        self.awaiting_codes = False
        if not known and not unknown:
            if not IMPORT_RE.search(suggest._norm(text)):
                return False                         # otra cosa: lo atiende el LLM
            self._import_excel()
        else:
            self._add_codes(known, unknown)
        if self.store.projects_initialized():
            self.ui.say(self.m("projects_ready", n=len(self.store.my_projects()),
                               a=self.p("add_project"), b=self.p("my_projects")))
            self._next_hint()
        else:
            self._ask_projects()
        return True

    def _codes_in_text(self, intent) -> tuple:
        known, unknown = database.extract_codes(self.text, self.status)
        code = (intent.project or "").upper()
        if code and code not in known and code not in unknown:
            (known if code in self.status else unknown).append(code)
        return known, unknown

    def _label(self, code: str, detail: str = "") -> str:
        info = self.status.get(code.upper(), {})
        name = info.get('description', '')[:40]
        label = f"{code} — {name}" if name else code
        if info.get('prorate'):
            label += "  · prorate"
        return f"{label}  · {detail}" if detail else label

    def _ensure_absence_categories(self):
        """Las categorías XX (licencias) existen en Outlook para todos; se crean las que falten."""
        try:
            created = self._pipeline().create_categories(list(config.INTERNAL_CODES))
        except Exception as e:                      # sin Outlook: no bloquea el arranque
            self.ui.log(f"⚠ Leave categories not checked: {e}")
            return
        if created:
            self.ui.say(self.m("absence_cats_created", names=", ".join(created)))

    def _create_categories(self, codes: List[str]) -> str:
        """Asegura la categoría de Outlook de cada código. Devuelve el resumen para el chat."""
        try:
            res = self._pipeline().ensure_categories(codes)
        except Exception as e:                      # sin Outlook: la lista igual se guarda
            self.ui.log(f"⚠ Outlook categories not created: {e}")
            return self.m("cats_failed")
        parts = []
        if res['created']:
            parts.append(self.m("cats_created", names=", ".join(res['created'])))
        if res['existing']:
            parts.append(self.m("cats_existing", names=", ".join(res['existing'])))
        return " ".join(parts)

    def _add_codes(self, codes: List[str], unknown: List[str] = ()):
        """Verifica los códigos con la base global y confirma en una tarjeta cuáles agregar."""
        mine = set(self.store.my_projects())
        notes, labels, already = [], {}, []
        for code in codes:
            info = self.status.get(code.upper())
            if code in mine:
                notes.append(self.m("frag_already", code=code))
                already.append(code)
            elif not info:
                notes.append(self.m("frag_missing", code=code))
            elif info['status'] != 'active':
                notes.append(self.m("frag_closed", code=code))
            else:
                labels[self._label(code)] = code
        notes += [self.m("frag_missing", code=c) for c in unknown]
        if notes:
            self.ui.say(self.m("codes_checked", details="; ".join(notes)))
        if already:                                 # ya en la lista: igual se revisa su categoría
            cats = self._create_categories(already)
            if cats:
                self.ui.say(cats)
        if not labels:
            return
        chosen = self.ui.decide(Decision(
            kind='add_projects', question="Add to my projects? (creates their Outlook categories)",
            options=list(labels), multi=True, preselected=list(labels)))
        if not chosen:
            self.ui.say(self.m("cancelled"))
            return
        codes = [labels[c] for c in chosen]
        self.store.add_projects(codes)
        cats = self._create_categories(codes)
        self.ui.say(self.m("projects_added", codes=", ".join(codes), cats=cats))

    def review_projects(self, charged: Optional[pd.DataFrame] = None):
        """
        Revisa "mis proyectos" contra la base global y el historial (cerrados,
        sin horas, con horas pero fuera de la lista) y propone los cambios en una tarjeta.
        """
        mine = self.store.my_projects()
        if not mine or not self.status:
            return
        added = {c: self.store.project_added(c) or '' for c in mine}
        props = analysis.review_projects(mine, self.status, self.store.all_hours(), charged,
                                         config.REVIEW_IDLE_MONTHS, added)
        since = (datetime.now() - timedelta(days=config.REVIEW_SNOOZE_DAYS)).isoformat()
        snoozed = self.store.dismissed(since)
        props = [p for p in props if (p['code'], p['reason']) not in snoozed]
        if not props:
            return

        notes = [self.m(f"frag_r_{p['reason']}", code=p['code'], months=p.get('months', ''),
                        hours=p.get('hours', '')) for p in props]
        self.ui.say(self.m("review_intro", details="; ".join(notes)))
        labels = {f"{'Remove' if p['action'] == 'remove' else 'Add'} "
                  f"{self._label(p['code'], p['detail'])}": p for p in props}
        chosen = self.ui.decide(Decision(
            kind='review_projects', question="Changes to my projects",
            options=list(labels), multi=True, preselected=list(labels)))
        if chosen is None:                          # cerrar = "ahora no" (se volverá a proponer)
            return
        apply = [labels[c] for c in chosen]
        kept = [p for p in props if p not in apply]
        for p in kept:
            self.store.dismiss(p['code'], p['reason'])
        add = [p['code'] for p in apply if p['action'] == 'add']
        remove = [p['code'] for p in apply if p['action'] == 'remove']
        if add:
            self.store.add_projects(add)
            self._create_categories(add)
        if remove:
            self.store.remove_projects(remove)
        if apply:
            self.ui.say(self.m("review_done", added=len(add), removed=len(remove),
                               n=len(self.store.my_projects())))
        if kept:
            self.ui.say(self.m("review_kept", days=config.REVIEW_SNOOZE_DAYS))

    def resume(self) -> bool:
        """
        Reconstruye el paso en curso desde los eventos del historial y los
        archivos ya generados; avisa cuál es el siguiente paso. True si dijo algo.
        """
        last = self.store.last_read()
        if not last:
            return False
        start = datetime.strptime(last['start'], '%Y-%m-%d')
        end = datetime.strptime(last['end'], '%Y-%m-%d')
        label = period_label(start, end)
        is_month = label == f"{start:%Y-%m}"
        if 'workday' in last['steps']:
            self.ui.say(self.m("resume_done", period=label, a=self.p("n4w", start),
                               b=self.p("read", datetime.now())))
            return True

        pipe = self._pipeline()
        path = pipe._path(config.TIMESHEET_NAME, start, end)
        if not os.path.exists(path):
            return False
        prorated = pipe._path(config.PRORATE_NAME, start, end)
        prorated = prorated if 'prorate' in last['steps'] and os.path.exists(prorated) else None
        self.loaded = Loaded(start, end, path, is_month, pipe.virtual_projects(path), prorated)

        when = last['at'][:16].replace('T', ' ')
        if self.loaded.virtual and not prorated:
            self.ui.say(self.m("resume_prorate", period=label, at=when,
                               codes=", ".join(self.loaded.virtual), phrase=self.p("prorate", start)))
            return True
        if is_month:
            self.ui.say(self.m("resume_workday", period=label, phrase=self.p("workday", start),
                               state="prorated" if prorated else f"read {when}"))
            return True
        return False

    # ── periodos ─────────────────────────────────────────────
    def _period(self, intent) -> tuple:
        """(start, end, is_month) desde fechas explícitas o un mes."""
        if intent.start_date and intent.end_date:
            return (datetime.strptime(intent.start_date, '%Y-%m-%d'),
                    datetime.strptime(intent.end_date, '%Y-%m-%d'), False)
        if intent.month:
            return (*timesheet.month_bounds(*workflows.parse_month(intent.month)), True)
        raise NeedInfo(self.m("need_period"))

    def _analysis_period(self, intent) -> tuple:
        """Periodo para análisis: el pedido → el leído en la sesión → el último del historial."""
        if intent.month or (intent.start_date and intent.end_date):
            return self._period(intent)[:2]
        if self.loaded:
            return self.loaded.start, self.loaded.end
        months = self.store.months()
        if months:
            return timesheet.month_bounds(*workflows.parse_month(months[-1]))
        raise NeedInfo(self.m("need_month"))

    def _history(self, start, end) -> pd.DataFrame:
        df = self.store.hours(start, end)
        if df.empty:
            raise NeedInfo(self.m("no_history", period=period_label(start, end),
                                  a=self.p("read", start), b=self.p("load_history")))
        return df

    def _require_loaded(self, wanted: Optional[str] = None) -> Loaded:
        if not self.loaded or (wanted and f"{self.loaded.start:%Y-%m}" != wanted):
            month = datetime.strptime(wanted, '%Y-%m') if wanted else self._last_month()
            raise NeedInfo(self.m("read_first", phrase=self.p("read", month)))
        return self.loaded

    def _alerts(self, start, end, df) -> List[str]:
        return analysis.alerts(df, start, end, self.store.all_hours(before=start),
                               self.store.targets(), config.EXPECTED_DAILY_HOURS,
                               config.ALERT_TARGET_TOLERANCE, config.ALERT_AVERAGE_DEVIATION)

    # ── PASOS ────────────────────────────────────────────────
    def do_read_hours(self, intent):
        start, end, is_month = self._period(intent)
        self._ensure_global()
        pipe = self._pipeline()
        findings = pipe.build_timesheet(start, end)

        self.store.save(findings['timesheet'], 'outlook', start, end)
        self.store.clear(start, end, 'prorated')          # una lectura nueva invalida el prorrateo
        self.store.log_event(start, end, 'read')
        virtual = pipe.virtual_projects(findings['path'])
        self.loaded = Loaded(start, end, findings['path'], is_month, virtual)

        label = self.loaded.label
        self.ui.show(f"Hours {label} (Outlook)", workflows.findings_report(findings))
        df = analysis.to_long(findings['timesheet'])
        report, flags = analysis.project_report(
            df, self.store.all_hours(before=start), self.store.targets(), self.status,
            config.ALERT_TARGET_TOLERANCE, self.store.my_projects())
        self.ui.show(f"Projects {label}", report)
        notes = self._alerts(start, end, df)
        if notes:
            self.ui.show(f"Alerts {label}", "\n".join(notes))

        balance = analysis.by_project(df)
        self.ui.say(self.m("read_done", period=label, total=analysis.h(balance['Hours'].sum()),
                           n=len(balance)))
        # lo importante, en pocas frases (el detalle está en las tarjetas)
        invalid = analysis.invalid_hours(df, self.status)     # según fechas de apertura / cierre
        if invalid:
            self.ui.show("⛔ Hours that cannot be uploaded", analysis.invalid_text(invalid))
            self.ui.say(self.m("blocked_projects", codes=", ".join(i['code'] for i in invalid)))
        if flags['off_target']:
            self.ui.say(self.m("off_target", codes=", ".join(flags['off_target'])))
        if flags['new']:
            self.ui.say(self.m("new_projects", codes=", ".join(flags['new'])))
        self.review_projects(df)                    # cerrados, sin horas, fuera de la lista
        if virtual:
            self.ui.say(self.m("next_prorate", codes=", ".join(virtual), phrase=self.p("prorate", start)))
        elif is_month:
            self.ui.say(self.m("next_workday", phrase=self.p("workday", start)))

        # dedicaciones que faltan: se preguntan en la conversación (las de más horas)
        self.pending_targets = [{'code': c, 'now': float(balance.loc[c, '%'])}
                                for c in flags['untargeted'][:config.TARGET_QUESTIONS_MAX]]
        if self.pending_targets:
            self._ask_target()
        else:
            self.ui.say(self.m("also_ask", a=self.p("compare", start), b=self.p("alerts", start)))

    # ── preguntas de dedicación (respuestas cortas sin LLM) ──
    def _ask_target(self):
        item = self.pending_targets[0]
        avg = analysis.project_averages(self.store.all_hours(before=self.loaded.start)
                                        if self.loaded else self.store.all_hours())
        avg_txt = f"{analysis.h(avg.loc[item['code'], 'Avg %'])}%" \
            if not avg.empty and item['code'] in avg.index else "-"
        asked = item.setdefault('i', None) or 0
        total = asked + len(self.pending_targets)
        self.ui.say(self.m("ask_target", i=asked + 1, n=total, code=item['code'],
                           now=analysis.h(item['now']), avg=avg_txt))

    def _answer_target(self, text: str) -> bool:
        """Interpreta "30%", "40 h", "igual", "omitir", "después". False → pasa al LLM."""
        t = suggest._norm(text).strip().rstrip('.!').strip()
        item = self.pending_targets[0]
        pct = hours = None
        if t in STOP_WORDS:
            self.pending_targets = []
            self.ui.say(self.m("targets_later", phrase=self.p("target", code=item['code'])))
            return True
        if t in SKIP_WORDS:
            self._next_target()
            return True
        if t in SAME_WORDS:
            pct = round(item['now'])
        else:
            match = TARGET_RE.fullmatch(t)
            if not match:
                self.pending_targets = []            # cambió de tema: lo atiende el LLM
                return False
            value = float(match.group(1).replace(',', '.'))
            if (match.group(2) or '%').startswith('h'):
                hours = value
            elif value <= 100:
                pct = value
            else:
                self.ui.say(self.m("need_target", code=item['code']))
                return True
        self.store.set_target(item['code'], pct, hours)
        self.ui.say(self.m("target_saved", code=item['code'],
                           target=analysis.target_label(self.store.targets()[item['code']]),
                           avg=f"{analysis.h(item['now'])}% (this month)"))
        self._next_target()
        return True

    def _next_target(self):
        done = self.pending_targets.pop(0)
        if self.pending_targets:
            self.pending_targets[0]['i'] = (done.get('i') or 0) + 1
            self._ask_target()
        elif self.loaded:
            start = self.loaded.start
            self.ui.say(self.m("also_ask", a=self.p("compare", start), b=self.p("alerts", start)))

    def do_prorate(self, intent):
        loaded = self._require_loaded(intent.month)
        if not loaded.virtual:
            self.ui.say(self.m("no_prorate_needed", period=loaded.label))
            return
        path = self._pipeline().prorate(loaded.path, loaded.start, loaded.end)
        loaded.prorated_path = path
        self.store.save(pd.read_csv(path), 'prorated', loaded.start, loaded.end)
        self.store.log_event(loaded.start, loaded.end, 'prorate', ", ".join(loaded.virtual))
        self.ui.say(self.m("prorate_done", phrase=self.p("workday", loaded.start)))

    def _guard_upload(self, df: pd.DataFrame, start):
        """Bloquea la subida si hay horas fuera de la vigencia de un proyecto (cerrado, sin abrir, inexistente)."""
        self._ensure_global()
        issues = analysis.invalid_hours(df, self.status)
        if issues:
            self.ui.show("⛔ Hours that cannot be uploaded", analysis.invalid_text(issues))
            raise NeedInfo(self.m("upload_blocked", codes=", ".join(i['code'] for i in issues),
                                  phrase=self.p("read", start)))

    def do_fill_workday(self, intent):
        # Una semana concreta (start_date = cualquier día de ella) dentro del mes leído
        sunday = None
        wanted = intent.month
        if intent.start_date:
            day = datetime.strptime(intent.start_date, '%Y-%m-%d')
            sunday = day - timedelta(days=(day.weekday() + 1) % 7)
            L = self.loaded
            overlaps = L and sunday <= L.end and sunday + timedelta(days=6) >= L.start
            if not wanted and not overlaps:
                wanted = f"{day:%Y-%m}"
        loaded = self._require_loaded(wanted)
        if not loaded.is_month:
            raise NeedInfo(self.m("workday_month_only", phrase=self.p("read", self._last_month())))
        if loaded.virtual and not loaded.prorated_path:
            raise NeedInfo(self.m("must_prorate", codes=", ".join(loaded.virtual),
                                  phrase=self.p("prorate", loaded.start)))

        csv_path = loaded.prorated_path or loaded.path
        df = analysis.to_long(pd.read_csv(csv_path))
        pipe = self._pipeline()
        source = "prorated" if loaded.prorated_path else "Outlook"
        if sunday is None:
            self._guard_upload(df, loaded.start)
            pipe._approve(f"Fill Workday {loaded.label} with these hours ({source})?",
                          analysis.balance_text(df, loaded.start, loaded.end, config.EXPECTED_DAILY_HOURS))
            if not self._fill(pipe, csv_path):
                return
            self.store.log_event(loaded.start, loaded.end, 'workday',
                                 analysis.table_text(analysis.by_project(df)[['Hours']]))
            loaded.workday_done = True
            self.ui.say(self.m("workday_done", period=loaded.label, a=self.p("n4w", loaded.start),
                               b=self.p("compare", loaded.start)))
            return

        # Regla del mes: de la semana solo cuentan los días del mes leído
        start, end = max(sunday, loaded.start), min(sunday + timedelta(days=6), loaded.end)
        label = f"{start:%Y-%m-%d} → {end:%Y-%m-%d}"
        week = df[(df['day'] >= f"{start:%Y-%m-%d}") & (df['day'] <= f"{end:%Y-%m-%d}")]
        if week.empty:
            raise NeedInfo(self.m("workday_week_empty", period=label))
        self._guard_upload(week, loaded.start)
        pipe._approve(f"Fill Workday week {label} with these hours ({source})?",
                      analysis.balance_text(week, start, end, config.EXPECTED_DAILY_HOURS))
        if not self._fill(pipe, csv_path, weeks_only=[f"{sunday:%Y-%m-%d}"]):
            return
        self.store.log_event(start, end, 'workday', analysis.table_text(analysis.by_project(week)[['Hours']]))
        self.ui.say(self.m("workday_week_done", period=label))

    def _fill(self, pipe, csv_path, weeks_only=None) -> bool:
        """Llena Workday; Guardar cada semana es irreversible → tarjeta roja. False si no se guardó."""
        save = lambda msg: self.ui.confirm_send(
            self.m("workday_save_title"), msg, self.m("workday_save_warning"),
            self.m("workday_save_ok"), self.m("workday_save_cancel"))
        try:
            pipe.fill_workday(csv_path, weeks_only=weeks_only, confirm_week=save)
        except Cancelled:
            self.ui.say(self.m("workday_not_saved"))
            return False
        return True

    def do_submit_n4w(self, intent):
        pipe = self._pipeline()
        if intent.start_date and intent.end_date:
            start, end = workflows.parse_weeks(intent.start_date, intent.end_date)
        elif intent.month:
            start, end = workflows.choose_n4w_weeks(pipe, *workflows.parse_month(intent.month))
        elif self.loaded:
            start, end = workflows.choose_n4w_weeks(pipe, self.loaded.start.year, self.loaded.start.month)
        else:
            raise NeedInfo(self.m("need_period"))

        self._ensure_global()
        findings = pipe.build_timesheet(start, end)
        self.store.save(findings['timesheet'], 'outlook', start, end)
        self._guard_upload(analysis.to_long(pd.read_csv(findings['path'])), start)
        pipe._approve(f"N4W {start:%Y-%m-%d} → {end:%Y-%m-%d}: hours OK?",
                      workflows.findings_report(findings))
        period = f"{start:%Y-%m-%d} → {end:%Y-%m-%d}"
        # Copiar a OneDrive = enviar a la base de N4W: confirmación explícita aparte
        sent = {}

        def send(rows, local):
            sent['summary'] = n4w.n4w_summary(rows)          # queda en el historial (auditoría)
            return self.ui.confirm_send(
                self.m("n4w_send_title", period=period), sent['summary'],
                self.m("n4w_send_warning"), self.m("n4w_send_ok"), self.m("n4w_send_cancel"))
        try:
            pipe.submit_n4w(findings['path'], start, end, confirm=send)
        except Cancelled as e:
            self.ui.say(self.m("n4w_not_sent", path=e.args[0] if e.args else ""))
            return
        self.store.log_event(start, end, 'n4w', sent.get('summary', ''))
        self.ui.say(self.m("n4w_done", period=period))

    def do_my_projects(self, intent):
        self._ensure_global()
        mine = self.store.my_projects()
        if not mine:
            self._ask_projects()
            return
        avg = analysis.project_averages(self.store.all_hours())
        targets = self.store.targets()
        rows = []
        for code in mine:
            info = self.status.get(code.upper(), {})
            rows.append({
                'Code': code, 'Description': info.get('description', '')[:32],
                'Global': analysis.STATUS_LABEL[analysis.global_status(code, self.status)]
                + (' · prorate' if info.get('prorate') else ''),
                'Avg %': analysis.h(avg.loc[code, 'Avg %']) if code in avg.index else '-',
                'Target': analysis.target_label(targets.get(code))})
        self.ui.show(f"My projects ({len(mine)})", pd.DataFrame(rows).set_index('Code').to_string())
        self.review_projects()

    def do_add_project(self, intent):
        self._ensure_global()
        known, unknown = self._codes_in_text(intent)
        if not known and not unknown:
            raise NeedInfo(self.m("need_codes"))
        self._add_codes(known, unknown)

    def do_remove_project(self, intent):
        self._ensure_global()
        known, unknown = self._codes_in_text(intent)
        codes = known + unknown
        if not codes:
            raise NeedInfo(self.m("need_codes"))
        mine = set(self.store.my_projects())
        notes = [self.m("frag_not_mine", code=c) for c in codes if c not in mine]
        if notes:
            self.ui.say(self.m("codes_checked", details="; ".join(notes)))
        labels = {self._label(c): c for c in codes if c in mine}
        if not labels:
            return
        chosen = self.ui.decide(Decision(
            kind='remove_projects', question="Remove from my projects? (Outlook categories are kept)",
            options=list(labels), multi=True, preselected=list(labels)))
        if not chosen:
            raise Cancelled()
        removed = [labels[c] for c in chosen]
        self.store.remove_projects(removed)
        self.ui.say(self.m("projects_removed", codes=", ".join(removed)))

    def do_import_projects(self, intent):
        self._ensure_global()
        if not self._import_excel() and not self.store.projects_initialized():
            self._ask_projects()

    def do_update_database(self, intent):
        """Vuelve a descargar la base global y revisa mis proyectos."""
        self.global_checked, self.status = False, {}
        self.check_global()
        self.review_projects()

    def do_categorize_meetings(self, intent):
        """Reuniones sin categoría del periodo → tarjeta con un proyecto sugerido por asunto → Outlook."""
        if intent.month or (intent.start_date and intent.end_date):
            start, end = self._period(intent)[:2]
        elif self.loaded:
            start, end = self.loaded.start, self.loaded.end
        else:
            start, end = timesheet.month_bounds(datetime.now().year, datetime.now().month)
        self._ensure_global()
        pipe = self._pipeline()
        mine = self.store.my_projects()
        res = pipe.ensure_categories(mine)                 # las de mis proyectos existen antes de asignar
        choices = sorted(res['created'] + res['existing'])
        label = period_label(start, end)

        groups = categorize.uncategorized_groups(pipe.calendar_entries(start, end))
        if not groups:
            self.ui.say(self.m("all_categorized", period=label))
            return
        history = pipe.calendar_entries(start - timedelta(days=config.CATEGORIZE_LOOKBACK_DAYS),
                                        start - timedelta(days=1))
        hint = categorize.suggestions(history, choices)
        shown = groups[:config.CATEGORIZE_MAX_ROWS]
        rows = {f"{g['subject'] or '(no subject)'}  ·  {g['n']}× · {analysis.h(g['hours'])} h": g for g in shown}
        chosen = self.ui.decide(Decision(
            kind='assign_categories', question=f"Meetings without category {label} — assign a project",
            options=choices, context={'rows': [{'label': k, 'default': hint.get(g['subject'])}
                                               for k, g in rows.items()], 'skip': '— skip —'}))
        if not chosen:
            self.ui.say(self.m("cancelled"))
            return
        done = sum(pipe.assign_category(rows[k]['subject'], rows[k]['starts'], cat)
                   for k, cat in chosen.items())
        left = sum(g['n'] for g in groups) - done
        self.ui.say(self.m("meetings_categorized", n=done, left=left, phrase=self.p("read", start)))

    def do_sync_categories(self, intent):
        mine = self.store.my_projects()
        if not mine:
            self._ask_projects()
            return
        self.ui.say(self.m("categories_synced", cats=self._create_categories(mine)))

    # ── ESTADO, CIERRE Y CORRECCIONES ────────────────────────
    def _status_period(self, intent) -> tuple:
        """Periodo pedido → el leído en la sesión → el mes del último leído → el mes pasado."""
        if intent.month or (intent.start_date and intent.end_date):
            return self._period(intent)[:2]
        if self.loaded:
            return self.loaded.start, self.loaded.end
        last = self.store.last_read()
        month = datetime.strptime(last['start'], '%Y-%m-%d') if last else self._last_month()
        return timesheet.month_bounds(month.year, month.month)

    @staticmethod
    def _covered(ev: pd.DataFrame, steps, start, end) -> Optional[str]:
        """Fecha del último evento de `steps` que cubre [start, end] completo (None si ninguno)."""
        s, e = f"{start:%Y-%m-%d}", f"{end:%Y-%m-%d}"
        hit = ev[ev['step'].isin(steps) & (ev['period_start'] <= s) & (ev['period_end'] >= e)]
        return hit['at'].max()[:16].replace('T', ' ') if len(hit) else None

    def _steps_status(self, start, end) -> tuple:
        """
        Estado de cada paso del periodo según el historial de eventos.
        Returns: (líneas de la tarjeta, frases de lo pendiente en orden)
        """
        ev = self.store.events(start, end)
        lines, todo = [], []
        read = self._covered(ev, ('read', 'history'), start, end)
        lines.append(f"① Read      {'✓ ' + read if read else '○ not read'}")
        if not read:
            todo.append(self.p("read", start))

        L = self.loaded if self.loaded and (self.loaded.start, self.loaded.end) == (start, end) else None
        prorated = self._covered(ev, ('prorate',), start, end)
        if prorated and (not L or L.prorated_path):
            lines.append(f"② Prorate   ✓ {prorated}")
        elif L and L.virtual:
            lines.append(f"② Prorate   ● pending: {', '.join(L.virtual)}")
            todo.append(self.p("prorate", start))
        elif L:
            lines.append("② Prorate   – not needed")

        # Workday: semanas domingo–sábado recortadas al periodo
        weeks, sunday = [], start - timedelta(days=(start.weekday() + 1) % 7)
        while sunday <= end:
            weeks.append((max(sunday, start), min(sunday + timedelta(days=6), end)))
            sunday += timedelta(days=7)
        fmt = lambda w: f"{w[0]:%m-%d}→{w[1]:%m-%d}"  # noqa: E731
        missing = [w for w in weeks if not self._covered(ev, ('workday',), *w)]
        lines.append(f"③ Workday   {'✓' if not missing else '●'} {len(weeks) - len(missing)}/{len(weeks)} weeks"
                     + (f" — pending: {', '.join(map(fmt, missing))}" if missing else ""))
        if missing:
            todo.append(self.p("workday", start))

        # N4W: semanas lunes–domingo que tocan el periodo
        n4w_weeks = timesheet.weeks_touching(start, end)
        missing = [w for w in n4w_weeks if not self._covered(ev, ('n4w',), *w)]
        lines.append(f"④ N4W       {'✓' if not missing else '●'} {len(n4w_weeks) - len(missing)}/{len(n4w_weeks)} weeks"
                     + (f" — pending: {', '.join(map(fmt, missing))}" if missing else ""))
        if missing:
            todo.append(self.p("n4w", start))

        sent = ev[ev['step'].isin(['workday', 'n4w'])]
        if len(sent):
            lines += ["", "Sent / saved:"]
            for r in sent.to_dict('records'):
                lines.append(f"  {r['at'][:16].replace('T', ' ')}  {'Workday' if r['step'] == 'workday' else 'N4W'}"
                             f"  {r['period_start']} → {r['period_end']}")
                lines += [f"      {x}" for x in (r['detail'] or '').splitlines()]
        return lines, todo

    def do_status(self, intent):
        """¿Qué me falta? / ¿Ya envié N4W…? / ¿Qué envié en agosto? — desde el historial de eventos."""
        start, end = self._status_period(intent)
        label = period_label(start, end)
        lines, todo = self._steps_status(start, end)
        self.ui.show(f"Status {label}", "\n".join(lines))
        if todo:
            self.ui.say(self.m("status_next", period=label, n=len(todo), phrase=todo[0]))
        else:
            self.ui.say(self.m("status_done", period=label, phrase=self.p("compare", start)))

    def do_close_check(self, intent):
        """¿Estoy listo para cerrar el mes? Días incompletos, reuniones sin categoría, bloqueos y pasos."""
        start, end = self._status_period(intent)
        label = period_label(start, end)
        df = self.store.hours(start, end)
        if df.empty:
            raise NeedInfo(self.m("read_first", phrase=self.p("read", start)))
        self._ensure_global()
        h, checks = analysis.h, []

        short = analysis.short_days(df, start, end, config.EXPECTED_DAILY_HOURS)
        days = ", ".join(f"{d[5:]} ({h(v)} h)" for d, v in short[:10]) + (" …" if len(short) > 10 else "")
        checks.append((not short, f"Days under {h(config.EXPECTED_DAILY_HOURS)} h: {days or 'none'}"))
        try:
            groups = categorize.uncategorized_groups(self._pipeline().calendar_entries(start, end))
            n, hours = sum(g['n'] for g in groups), sum(g['hours'] for g in groups)
            checks.append((not groups, f"Meetings without category: {n} ({h(hours)} h)"
                           + (f" → “{self.p('categorize', start)}”" if groups else "")))
        except Exception as e:
            self.ui.log(f"⚠ Outlook not read: {e}")
            checks.append((False, "Meetings without category: could not read Outlook"))
        holidays = holidays_cal.missing_absences(
            df, holidays_cal.public_holidays(self._country(), start, end))
        checks.append((not holidays, "Public holidays without Public Holiday (XX05): "
                       + (", ".join(f"{d[5:]} {n}" for d, n in holidays) or "none")))
        blocked = analysis.invalid_hours(df, self.status)
        checks.append((not blocked, "Hours on closed / not opened projects: "
                       + (", ".join(i['code'] for i in blocked) or "none")))

        steps, _ = self._steps_status(start, end)
        lines = [("✓ " if ok else "⚠ ") + text for ok, text in checks] + ["", *steps]
        self.ui.show(f"Close check {label}", "\n".join(lines))
        issues = sum(not ok for ok, _ in checks)
        self.ui.say(self.m("close_issues", period=label, n=issues) if issues
                    else self.m("close_ready", period=label))

    def do_edit_hours(self, intent):
        """Corrige las horas de un proyecto en un día del periodo leído (solo el archivo para Workday)."""
        loaded = self._require_loaded()
        if not intent.project or not intent.start_date or intent.hours is None:
            raise NeedInfo(self.m("need_edit", phrase=self.p("edit")))
        code, day, new = intent.project, intent.start_date, float(intent.hours)
        if loaded.prorated_path and code in loaded.virtual:
            raise NeedInfo(self.m("edit_virtual", code=code))
        path = loaded.prorated_path or loaded.path
        ts = pd.read_csv(path)
        col = next((c for c in get_date_columns(ts) if str(c)[:10] == day), None)
        if col is None:
            raise NeedInfo(self.m("edit_out_of_period", day=day, period=loaded.label))

        match = ts.index[ts['Code'].astype(str).str.upper() == code]
        if len(match):
            idx = match[0]
        else:                                           # proyecto sin horas en el periodo: nueva fila
            cat = self._pipeline().catalog().drop_duplicates('Code').set_index('Code')
            if code not in cat.index:
                raise NeedInfo(self.m("codes_checked", details=self.m("frag_missing", code=code)))
            idx = len(ts)
            ts.loc[idx] = 0.0
            ts.loc[idx, 'Code'] = code
            for c in ('Task Name', 'Grant ID'):
                if c in ts.columns:
                    ts.loc[idx, c] = cat.loc[code, c]
        h = analysis.h
        old = float(ts.loc[idx, col])
        before = float(ts[col].sum())
        after = before - old + new
        weekday = datetime.strptime(day, '%Y-%m-%d').strftime('%a')
        self._pipeline()._approve(
            f"Change {code} on {day}?",
            f"{code}   {day} ({weekday}):  {h(old)} h → {h(new)} h\n"
            f"Day total:  {h(before)} h → {h(after)} h\n\n"
            f"Only {os.path.basename(path)} (the file for Workday) changes. Outlook is not modified.")
        ts.loc[idx, col] = new
        ts.to_csv(path, index=False)
        self.store.save(ts, 'prorated' if loaded.prorated_path else 'outlook', loaded.start, loaded.end)
        self.store.log_event(loaded.start, loaded.end, 'edit', f"{code} {day}: {h(old)} → {h(new)} h")
        self.ui.say(self.m("edit_done", code=code, day=day, old=h(old), new=h(new), total=h(after)))
        d = datetime.strptime(day, '%Y-%m-%d')
        if self._covered(self.store.events(d, d), ('workday',), d, d):
            self.ui.say(self.m("edit_workday_again"))

    def do_explain_prorate(self, intent):
        """¿Por qué prorrateaste así? — antes/después y la regla aplicada a cada proyecto."""
        loaded = self._require_loaded(intent.month)
        if not loaded.virtual:
            self.ui.say(self.m("no_prorate_needed", period=loaded.label))
            return
        if not loaded.prorated_path:
            raise NeedInfo(self.m("no_prorate_yet", period=loaded.label, phrase=self.p("prorate", loaded.start)))
        before, after = pd.read_csv(loaded.path), pd.read_csv(loaded.prorated_path)
        self.ui.show(f"Prorate {loaded.label} — how it was split",
                     analysis.prorate_comparison(before, after, loaded.virtual) + "\n\n"
                     + analysis.prorate_explanation(before, after, loaded.virtual))

    # ── ANÁLISIS ─────────────────────────────────────────────
    def _chart(self, spec: Optional[dict]):
        """Las gráficas acompañan al texto: si fallan, el análisis igual se muestra."""
        if not spec or not hasattr(self.ui, "chart"):
            return
        try:
            self.ui.chart(spec)
        except Exception as e:
            self.ui.log(f"⚠ Chart not shown: {e}")

    def _period_charts(self, df, start, end):
        label = period_label(start, end)
        self._chart(charts.share_chart(df, f"Hours by project {label}"))
        self._chart(charts.daily_chart(df, start, end, config.EXPECTED_DAILY_HOURS, f"Hours per day {label}"))

    def do_hours_summary(self, intent):
        if intent.project or self._short_range(intent):
            self._quick_hours(intent)                       # pregunta puntual → una frase
            return
        start, end = self._analysis_period(intent)
        df = self._history(start, end)
        self.ui.show(f"Summary {period_label(start, end)}",
                     analysis.balance_text(df, start, end, config.EXPECTED_DAILY_HOURS))
        self._period_charts(df, start, end)

    @staticmethod
    def _short_range(intent) -> bool:
        if not (intent.start_date and intent.end_date):
            return False
        days = datetime.strptime(intent.end_date, '%Y-%m-%d') - datetime.strptime(intent.start_date, '%Y-%m-%d')
        return days.days < 7

    def _quick_hours(self, intent):
        """
        "¿Cuántas horas llevo esta semana / en X en septiembre?". Un periodo ya leído
        y cerrado sale del historial; uno en curso se lee de Outlook (hasta hoy, sin guardar).
        """
        start, end = self._analysis_period(intent)
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        src = ""
        if end < today and self.store.was_read(start, end):
            df = self.store.hours(start, end)
        else:
            end = max(start, min(end, today))
            self._ensure_global()
            try:
                df = analysis.to_long(self._pipeline().build_timesheet(start, end, save_files=False)['timesheet'])
            except ValueError:                              # sin reuniones en el periodo
                df = pd.DataFrame(columns=analysis.LONG_COLUMNS)
            src = self.m("from_outlook")
        label, h = period_label(start, end), analysis.h
        table = analysis.by_project(df)
        total = float(table['Hours'].sum())
        if intent.project:
            code = intent.project
            if code not in table.index:
                self.ui.say(self.m("quick_project_none", code=code, period=label, src=src))
                return
            self.ui.say(self.m("quick_project", code=code, hours=h(table.loc[code, 'Hours']), period=label,
                               pct=h(table.loc[code, '%']), total=h(total), src=src))
            return
        days = analysis.working_days(start, end)
        top = ", ".join(f"{c} {h(r['Hours'])} h" for c, r in table.head(3).iterrows()) or "-"
        self.ui.say(self.m("quick_total", period=label, total=h(total), days=days, src=src, top=top,
                           expected=h(days * config.EXPECTED_DAILY_HOURS)))

    def do_show_chart(self, intent):
        """Gráfica pedida: de un proyecto (tendencia), de un periodo (distribución y días) o de varios meses."""
        if intent.project:
            df = self.store.all_hours()
            spec = charts.trend_chart(df, intent.project, self.store.targets().get(intent.project))
            if spec is None:
                raise NeedInfo(self.m("unknown_project", code=intent.project))
            self._chart(spec)
            return
        if intent.month or (intent.start_date and intent.end_date):
            start, end = self._period(intent)[:2]
            df = self._history(start, end)
            if start.strftime('%Y-%m') == end.strftime('%Y-%m'):
                self._period_charts(df, start, end)
            else:
                self._chart(charts.months_chart(df, f"Hours per month {period_label(start, end)}"))
            return
        df = self.store.all_hours()
        if df.empty:
            raise NeedInfo(self.m("history_empty", a=self.p("read", self._last_month()),
                                  b=self.p("load_history")))
        if intent.months_back:
            first = (datetime.now().replace(day=1) - pd.DateOffset(months=int(intent.months_back)))
            df = df[df['day'] >= f"{first:%Y-%m-%d}"]
        self._chart(charts.months_chart(df))

    def do_compare_months(self, intent):
        start_a, end_a = self._analysis_period(intent)
        if intent.month2:
            start_b, end_b = timesheet.month_bounds(*workflows.parse_month(intent.month2))
        else:
            prev = start_a - timedelta(days=1)
            start_b, end_b = timesheet.month_bounds(prev.year, prev.month)
        a, b = period_label(start_a, end_a), period_label(start_b, end_b)
        df_a, df_b = self._history(start_a, end_a), self._history(start_b, end_b)
        self.ui.show(f"{a} vs {b}", analysis.compare_text(df_a, df_b, a, b))
        self._chart(charts.compare_chart(df_a, df_b, a, b))

    def do_project_stats(self, intent):
        df = self.store.all_hours()
        if df.empty:
            raise NeedInfo(self.m("history_empty", a=self.p("read", self._last_month()),
                                  b=self.p("load_history")))
        targets = self.store.targets()
        if intent.project:
            text = analysis.project_text(df, intent.project, targets.get(intent.project))
            if text is None:
                raise NeedInfo(self.m("unknown_project", code=intent.project))
            self.ui.show(f"Project {intent.project}", text)
            self._chart(charts.trend_chart(df, intent.project, targets.get(intent.project)))
        else:
            self.ui.show("Project averages", analysis.averages_text(df, targets))
            self._chart(charts.months_chart(df))

    def do_set_target(self, intent):
        if not intent.project:
            raise NeedInfo(self.m("need_project"))
        if intent.target_pct is None and intent.target_hours is None:
            raise NeedInfo(self.m("need_target", code=intent.project))
        self.store.set_target(intent.project, intent.target_pct, intent.target_hours)
        avg = analysis.project_averages(self.store.all_hours())
        avg_txt = "-"
        if not avg.empty and intent.project in avg.index:
            row = avg.loc[intent.project]
            avg_txt = f"{analysis.h(row['Avg h'])} h ({analysis.h(row['Avg %'])}%)"
        self.ui.say(self.m("target_saved", code=intent.project,
                           target=analysis.target_label(self.store.targets()[intent.project]),
                           avg=avg_txt))

    def do_alerts(self, intent):
        start, end = self._analysis_period(intent)
        notes = self._alerts(start, end, self._history(start, end))
        label = period_label(start, end)
        if notes:
            self.ui.show(f"Alerts {label}", "\n".join(notes))
        else:
            self.ui.say(self.m("no_alerts", period=label))

    def do_load_history(self, intent):
        n = max(1, min(int(intent.months_back or config.HISTORY_DEFAULT_MONTHS), 24))
        self._ensure_global()
        pipe = self._pipeline()
        first = datetime.now().replace(day=1)
        done = skipped = failed = 0
        for i in range(n, 0, -1):                       # meses completos anteriores al actual
            month = (first - pd.DateOffset(months=i)).to_pydatetime()
            ym = f"{month:%Y-%m}"
            start, end = timesheet.month_bounds(month.year, month.month)
            if self.store.was_read(start, end):
                skipped += 1
                continue
            try:
                findings = pipe.build_timesheet(start, end, save_files=False)
            except ValueError as e:
                self.ui.log(f"  {ym}: {e}")
                failed += 1
                continue
            self.store.save(findings['timesheet'], 'outlook', start, end)
            self.store.log_event(start, end, 'history')
            self.ui.log(f"  ✓ {ym} saved")
            done += 1
        self.ui.say(self.m("history_loaded", done=done, skipped=skipped, failed=failed))
