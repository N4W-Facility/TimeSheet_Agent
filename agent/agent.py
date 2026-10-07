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
from core import analysis, database, timesheet
from core.history import History
from pipeline import Callbacks, Cancelled, Decision, Pipeline


class AgentUI(Protocol):
    def say(self, text: str): ...
    def log(self, text: str): ...
    def show(self, title: str, detail: str): ...                # tarjeta informativa
    def decide(self, decision: Decision): ...                   # bloqueante
    def approve(self, title: str, detail: str) -> bool: ...     # bloqueante
    def pick_file(self, title: str) -> Optional[str]: ...       # explorador de archivos (bloqueante)


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
NEEDS_PROJECTS = {"read_hours", "prorate", "fill_workday", "submit_n4w", "load_history"}

# Respuestas cortas a "¿cuál debería ser tu dedicación a X?" (se interpretan sin LLM)
SAME_WORDS = {"same", "keep", "ok", "yes", "igual", "si", "asi", "mantener", "mesmo", "sim", "manter"}
SKIP_WORDS = {"skip", "next", "no", "omitir", "saltar", "siguiente", "pasar", "pular", "nao", "proximo"}
STOP_WORDS = {"stop", "later", "cancel", "parar", "despues", "luego", "cancelar", "depois", "mais tarde"}
ANSWER_WORDS = {"en": ("same", "skip"), "es": ("igual", "omitir"), "pt": ("mesmo", "pular")}
# "importar mi Excel" → explorador de archivos (sin LLM)
IMPORT_RE = re.compile(r"\b(import\w*|excel|xlsx)\b")
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
                             has_history=True, top_code=self._top_code())

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
        return Pipeline(email=self.settings.email, callbacks=cb)

    def _ensure_global(self):
        """Base global descargada una vez por sesión (antes de leer Outlook)."""
        if not self.global_checked:
            self.check_global()
        if not self.status:
            self.status = self._pipeline().task_status()

    def _remember(self, role: str, content: str):
        self.chat_history.append({"role": role, "content": content})
        self.chat_history = self.chat_history[-12:]

    # ── entrada principal (se llama desde un hilo de trabajo) ─
    def handle(self, text: str):
        if self.pending_targets and self._answer_target(text):
            return
        if self.awaiting_codes and self._answer_codes(text):
            return
        self.text = text
        try:
            intent = llm.parse_intent(text, self.chat_history)
        except Exception as e:
            self.ui.log(traceback.format_exc())
            self.ui.say(self.m("llm_down", err=e))
            return

        self.lang = intent.language or self.lang
        if self.lang != self.settings.language:      # el saludo y las sugerencias usan este idioma
            self.settings.language = self.lang
            try:
                self.settings.save()
            except OSError:
                pass
        self._remember("user", text)
        if intent.reply:
            self.ui.say(intent.reply)
            self._remember("assistant", intent.reply)
        self.ui.log(f"[intent] {intent}")

        if intent.action in ("help", "other"):
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

    def _create_categories(self, codes: List[str]) -> List[str]:
        try:
            return self._pipeline().create_categories(codes)
        except Exception as e:                      # sin Outlook: la lista igual se guarda
            self.ui.log(f"⚠ Outlook categories not created: {e}")
            return []

    def _add_codes(self, codes: List[str], unknown: List[str] = ()):
        """Verifica los códigos con la base global y confirma en una tarjeta cuáles agregar."""
        mine = set(self.store.my_projects())
        notes, labels = [], {}
        for code in codes:
            info = self.status.get(code.upper())
            if code in mine:
                notes.append(self.m("frag_already", code=code))
            elif not info:
                notes.append(self.m("frag_missing", code=code))
            elif info['status'] != 'active':
                notes.append(self.m("frag_closed", code=code))
            else:
                labels[self._label(code)] = code
        notes += [self.m("frag_missing", code=c) for c in unknown]
        if notes:
            self.ui.say(self.m("codes_checked", details="; ".join(notes)))
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
        created = self._create_categories(codes)
        self.ui.say(self.m("projects_added", codes=", ".join(codes), n=len(created)))

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
        if flags['blocked']:
            self.ui.say(self.m("blocked_projects", codes=", ".join(flags['blocked'])))
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
            pipe._approve(f"Fill Workday {loaded.label} with these hours ({source})?",
                          analysis.balance_text(df, loaded.start, loaded.end, config.EXPECTED_DAILY_HOURS))
            pipe.fill_workday(csv_path)
            self.store.log_event(loaded.start, loaded.end, 'workday')
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
        pipe._approve(f"Fill Workday week {label} with these hours ({source})?",
                      analysis.balance_text(week, start, end, config.EXPECTED_DAILY_HOURS))
        pipe.fill_workday(csv_path, weeks_only=[f"{sunday:%Y-%m-%d}"])
        self.store.log_event(start, end, 'workday')
        self.ui.say(self.m("workday_week_done", period=label))

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
        pipe._approve(f"N4W {start:%Y-%m-%d} → {end:%Y-%m-%d}: hours OK?",
                      workflows.findings_report(findings))
        pipe.submit_n4w(findings['path'], start, end)
        self.store.log_event(start, end, 'n4w')
        self.ui.say(self.m("n4w_done", period=f"{start:%Y-%m-%d} → {end:%Y-%m-%d}"))

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

    def do_sync_categories(self, intent):
        created = self._pipeline().create_categories(self.store.my_projects())
        self.ui.say(self.m("categories_synced", n=len(created)))

    # ── ANÁLISIS ─────────────────────────────────────────────
    def do_hours_summary(self, intent):
        start, end = self._analysis_period(intent)
        df = self._history(start, end)
        self.ui.show(f"Summary {period_label(start, end)}",
                     analysis.balance_text(df, start, end, config.EXPECTED_DAILY_HOURS))

    def do_compare_months(self, intent):
        start_a, end_a = self._analysis_period(intent)
        if intent.month2:
            start_b, end_b = timesheet.month_bounds(*workflows.parse_month(intent.month2))
        else:
            prev = start_a - timedelta(days=1)
            start_b, end_b = timesheet.month_bounds(prev.year, prev.month)
        a, b = period_label(start_a, end_a), period_label(start_b, end_b)
        text = analysis.compare_text(self._history(start_a, end_a), self._history(start_b, end_b), a, b)
        self.ui.show(f"{a} vs {b}", text)

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
        else:
            self.ui.show("Project averages", analysis.averages_text(df, targets))

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
