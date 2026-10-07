"""Flujos y agente con LLM y pipeline simulados (sin Ollama, Outlook ni navegador)."""
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import workflows  # noqa: E402
from agent import agent as agent_mod  # noqa: E402
from agent import llm, suggest  # noqa: E402
from agent.settings import Settings  # noqa: E402
from core import timesheet  # noqa: E402
from core.history import History  # noqa: E402
from pipeline import Callbacks, Cancelled, Pipeline  # noqa: E402


class FakeUI:
    def __init__(self, choice=None):
        self.said, self.logs, self.cards, self.choice, self.decisions = [], [], [], choice, []
        self.charts = []

    def say(self, text): self.said.append(text)
    def log(self, text): self.logs.append(text)
    def show(self, title, detail): self.cards.append((title, detail))
    def chart(self, spec): self.charts.append(spec)
    def decide(self, d):
        self.decisions.append(d)
        if self.choice:
            return self.choice(d)
        return list(d.preselected) if d.multi else None
    def approve(self, title, detail): return True

    def pick_file(self, title):
        self.picked = title
        return getattr(self, 'file', None)


def make_pipe(tmp_path, decide):
    return Pipeline(str(tmp_path), callbacks=Callbacks(decide=decide))


# ── semanas N4W ──────────────────────────────────────────────

def test_choose_n4w_weeks_returns_span(tmp_path):
    pipe = make_pipe(tmp_path, lambda d: d.options[1:4])
    assert workflows.choose_n4w_weeks(pipe, 2026, 10) == (datetime(2026, 10, 5), datetime(2026, 10, 25))


def test_choose_n4w_weeks_rejects_gaps(tmp_path):
    pipe = make_pipe(tmp_path, lambda d: [d.options[0], d.options[2]])
    with pytest.raises(ValueError):
        workflows.choose_n4w_weeks(pipe, 2026, 10)


def test_choose_n4w_weeks_cancel(tmp_path):
    pipe = make_pipe(tmp_path, lambda d: None)
    with pytest.raises(Cancelled):
        workflows.choose_n4w_weeks(pipe, 2026, 10)


# ── agente ───────────────────────────────────────────────────

def _intent(action, **kw):
    return llm.Intent(**{"action": action, "language": "en", "reply": "ok", **kw})


class FakePipe:
    """Mes con P100 (6 h/día laborable) y VIRT1 (2 h/día, se prorratea)."""

    def __init__(self, tmp_path, virtual=("VIRT1",)):
        self.tmp, self.virtual = tmp_path, list(virtual)
        self.approved, self.filled, self.refreshes, self.categories = [], None, 0, []
        self.outlook = set()        # códigos con categoría ya existente en Outlook
        self.assigned = []
        self.status = {
            'P100': {'status': 'active', 'prorate': False, 'description': 'Project', 'opened': '2020-01-01', 'closed': None},
            'P200': {'status': 'closed', 'prorate': False, 'description': 'Old', 'opened': '2020-01-01', 'closed': '2026-08-31'},
            'P300': {'status': 'active', 'prorate': False, 'description': 'Other', 'opened': '2020-01-01', 'closed': None},
            'VIRT1': {'status': 'active', 'prorate': True, 'description': 'Virtual', 'opened': '2020-01-01', 'closed': None}}

    def refresh_task_details(self):
        self.refreshes += 1
        return True, "2026-10-06 19:00"

    def task_status(self):
        return self.status

    def calendar_entries(self, start, end):
        if start.month == 10:
            return [{'subject': 'Weekly sync', 'start': datetime(2026, 10, 5, 9), 'hours': 1.0, 'categories': ''},
                    {'subject': 'Weekly sync', 'start': datetime(2026, 10, 12, 9), 'hours': 1.0, 'categories': ''},
                    {'subject': 'Coffee', 'start': datetime(2026, 10, 6, 9), 'hours': 0.5, 'categories': ''}]
        return [{'subject': 'Weekly sync', 'start': datetime(2026, 9, 7, 9), 'hours': 1.0, 'categories': 'P100'}]

    def assign_category(self, subject, starts, category):
        self.assigned.append((subject, len(starts), category))
        return len(starts)

    def ensure_categories(self, codes):
        self.categories += list(codes)
        existing = [f"{c} | old name" for c in codes if c in self.outlook]
        return {'created': [c for c in codes if c not in self.outlook], 'existing': existing}

    def build_timesheet(self, start, end, save_files=True):
        days = [d for d in pd.date_range(start, end) if d.weekday() < 5]
        df = pd.DataFrame({'Code': ['P100', 'VIRT1'], 'Task Name': ['Project', 'Virtual'],
                           'Grant ID': ['G1', 'G2']})
        for d in days:
            df[d.strftime('%Y-%m-%d 00:00:00')] = [6.0, 2.0]
        path = self.tmp / f"ts_{start:%Y%m%d}.csv"
        df.to_csv(path, index=False)
        return {'path': str(path), 'timesheet': df, 'start': start, 'end': end,
                'summary': timesheet.summarize(df), 'unmapped': {}, 'irregular_days': []}

    def virtual_projects(self, csv_path):
        return self.virtual

    def prorate(self, csv_path, start, end):
        df = pd.read_csv(csv_path)
        cols = [c for c in df.columns if c[:4].isdigit()]
        df.loc[df['Code'] == 'P100', cols] = 8.0
        df = df[df['Code'] != 'VIRT1']
        path = self.tmp / "prorated.csv"
        df.to_csv(path, index=False)
        return str(path)

    def _approve(self, title, detail):
        self.approved.append(title)

    def fill_workday(self, csv_path, weeks_only=None):
        self.filled = csv_path
        self.weeks_only = weeks_only


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Agente con BD válida, historial temporal y pipeline simulado."""
    monkeypatch.setattr(Settings, "save", lambda self: None)   # no escribir settings.json real
    ui = FakeUI()
    store = History(str(tmp_path / "h.db"))
    store.add_projects(['P100', 'VIRT1'])
    agent = agent_mod.Agent(ui, Settings(email="me@tnc.org"), store=store)
    pipe = FakePipe(tmp_path)
    monkeypatch.setattr(agent, "_pipeline", lambda: pipe)

    def send(action, **kw):
        monkeypatch.setattr(llm, "parse_intent", lambda t, h: _intent(action, **kw))
        agent.handle("...")
        return ui.said[-1] if ui.said else ""
    return agent, ui, pipe, send


def test_agent_help_needs_no_settings(monkeypatch):
    monkeypatch.setattr(Settings, "save", lambda self: None)
    monkeypatch.setattr(llm, "parse_intent", lambda t, h: _intent("help", reply="I can read hours"))
    ui = FakeUI()
    agent_mod.Agent(ui, Settings()).handle("what can you do?")
    assert ui.said == ["I can read hours"]


def test_read_without_projects_asks_for_codes(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "save", lambda self: None)
    monkeypatch.setattr(llm, "parse_intent", lambda t, h: _intent("read_hours", month="2026-09"))
    ui = FakeUI()
    agent = agent_mod.Agent(ui, Settings(), store=History(str(tmp_path / "h.db")))
    agent.handle("read september")
    assert "which projects are you working on" in ui.said[-1]
    assert agent.awaiting_codes


def test_read_asks_period(env):
    _, _, _, send = env
    assert send("read_hours").startswith("Which period?")


def test_workday_requires_read_first(env):
    _, _, pipe, send = env
    assert send("fill_workday", month="2026-09").startswith("First read your hours")
    assert pipe.filled is None


def test_step_by_step_flow_with_mandatory_prorate(env):
    agent, ui, pipe, send = env
    send("read_hours", month="2026-09")
    assert agent.loaded.virtual == ["VIRT1"]
    assert any(t.startswith("Hours 2026-09") for t, _ in ui.cards)
    assert "must be prorated" in ui.said[-2]        # [-1] = pista extra (objetivos/análisis)

    # Workday sin prorrateo → bloqueado
    assert "must be prorated" in send("fill_workday")
    assert pipe.filled is None

    send("prorate")
    assert agent.loaded.prorated_path.endswith("prorated.csv")

    send("fill_workday")
    assert pipe.filled.endswith("prorated.csv")
    assert pipe.approved and pipe.approved[-1].startswith("Fill Workday 2026-09")
    assert pipe.refreshes == 1       # base global: una vez por sesión


def test_workday_rejects_non_month_period(env):
    agent, _, pipe, send = env
    pipe.virtual = []
    send("read_hours", start_date="2026-09-07", end_date="2026-09-13")
    assert "full calendar month" in send("fill_workday")


def test_history_summary_compare_and_targets(env):
    agent, ui, pipe, send = env
    pipe.virtual = []
    assert "no saved hours" in send("hours_summary", month="2026-08")

    send("read_hours", month="2026-08")
    send("read_hours", month="2026-09")
    send("hours_summary", month="2026-09")
    title, detail = ui.cards[-1]
    assert title == "Summary 2026-09" and "P100" in detail

    send("compare_months", month="2026-09")
    assert ui.cards[-1][0] == "2026-09 vs 2026-08"

    msg = send("set_target", project="P100", target_pct=50)
    assert "50%" in msg and "75%" in msg     # promedio real: 6 de 8 h

    send("alerts", month="2026-09")
    assert any("P100" in line and "target 50%" in line for line in ui.cards[-1][1].splitlines())


def test_prorated_hours_are_what_history_reports(env):
    agent, ui, pipe, send = env
    send("read_hours", month="2026-09")
    send("prorate")
    send("project_stats", project="VIRT1")
    assert "no hours" in ui.said[-1]          # tras prorratear, VIRT1 ya no cuenta como cargado


def test_resume_previous_session(env, tmp_path):
    agent, ui, pipe, send = env
    send("read_hours", month="2026-09")

    # Nueva sesión: mismo historial, archivos en disco
    ui2 = FakeUI()
    agent2 = agent_mod.Agent(ui2, agent.settings, store=agent.store)
    pipe.tmp = tmp_path
    agent2._pipeline = lambda: type("P", (), {
        "_path": lambda self, name, s, e: str(tmp_path / f"ts_{s:%Y%m%d}.csv") if "02-" in name
        else str(tmp_path / "prorated.csv"),
        "virtual_projects": lambda self, p: ["VIRT1"]})()
    agent2.resume()
    assert agent2.loaded and agent2.loaded.start == datetime(2026, 9, 1)
    assert "still must be prorated" in ui2.said[-1]

    send("prorate")
    agent3 = agent_mod.Agent(FakeUI(), agent.settings, store=agent.store)
    agent3._pipeline = agent2._pipeline
    agent3.resume()
    assert agent3.loaded.prorated_path.endswith("prorated.csv")
    assert "fill Workday" in agent3.ui.said[-1]

    send("fill_workday")
    agent4 = agent_mod.Agent(FakeUI(), agent.settings, store=agent.store)
    agent4.resume()
    assert agent4.loaded is None and "Workday filled for 2026-09" in agent4.ui.said[-1]


# ── sugerencias ──────────────────────────────────────────────

def test_suggestions_follow_the_steps(env):
    agent, ui, pipe, send = env
    assert agent.progress().startswith("① Read ○")
    assert agent.suggestions()[0].startswith("read my hours for")

    send("read_hours", month="2026-09")
    assert agent.suggestions()[:2] == ["same", "skip"]      # pregunta de dedicación abierta
    assert "“prorate the hours for" in ui.said[-2]          # el mensaje cita la frase sugerida
    agent.handle("skip")
    assert agent.suggestions()[0] == suggest.phrase("prorate", "en", datetime(2026, 9, 1))
    assert "② Prorate ●" in agent.progress()

    send("prorate")
    assert agent.suggestions()[0].startswith("fill Workday for")
    send("fill_workday")
    assert "③ Workday ✓" in agent.progress()
    assert agent.suggestions()[0].startswith("submit N4W for")


def test_language_is_remembered_for_suggestions(env, monkeypatch):
    agent, ui, pipe, send = env
    monkeypatch.setattr(llm, "parse_intent", lambda t, h: llm.Intent(action="help", language="es"))
    agent.handle("hola")
    assert agent.settings.language == "es"
    assert agent.suggestions()[0].startswith("lee mis horas de")


def test_greet_examples_without_pending_step(env):
    agent, ui, pipe, send = env
    agent.greet()
    assert ui.said[0].startswith("Hi!") and "To start" in ui.said[-1]


def test_match_ignores_accents_and_case():
    pool = suggest.phrases(suggest.State(), "es")
    assert any("historial" in p for p in suggest.match("HISTO", pool))
    assert suggest.match("dedicacion", pool) == [p for p in pool if "dedicación" in p]
    assert suggest.match("", pool) == []


# ── mis proyectos ────────────────────────────────────────────

def test_onboarding_asks_and_validates_codes(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "save", lambda self: None)
    ui, pipe = FakeUI(), FakePipe(tmp_path)
    agent = agent_mod.Agent(ui, Settings(), store=History(str(tmp_path / "h.db")))
    agent._pipeline = lambda: pipe
    agent.greet()
    assert "which projects are you working on" in ui.said[-1]

    agent.handle("I work on p100, VIRT1, P200 and ZZ9999")      # sin LLM
    checked = next(t for t in ui.said if t.startswith("Checked"))
    assert "P200 is closed" in checked and "ZZ9999 does not exist" in checked
    assert ui.decisions[-1].preselected == ui.decisions[-1].options
    assert agent.store.my_projects() == ['P100', 'VIRT1']
    assert pipe.categories == ['P100', 'VIRT1']
    assert any(t.startswith("Your projects: 2") for t in ui.said)


def test_legacy_excel_is_imported_once(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "save", lambda self: None)
    old = tmp_path / "old.xlsx"
    pd.DataFrame({'Code': ['XX01', 'P100', 'P200'], 'Include': [1, 1, 1]}).to_excel(
        old, sheet_name="N4W-Projects", index=False)
    ui, pipe = FakeUI(), FakePipe(tmp_path)
    agent = agent_mod.Agent(ui, Settings(db_path=str(old)), store=History(str(tmp_path / "h.db")))
    agent._pipeline = lambda: pipe
    agent.greet()
    assert any("old projects Excel with 2 codes" in t for t in ui.said)
    assert agent.store.my_projects() == ['P100']                # P200 cerrado: no se ofrece
    assert not agent.awaiting_codes


def test_review_proposes_and_remembers_rejections(env):
    agent, ui, pipe, send = env
    agent.store.remove_projects(['VIRT1'])
    agent.store.add_projects(['P200'])                          # cerrado en la base global
    pipe.virtual = []

    def keep_unlisted(d):
        return [o for o in d.options if o.startswith("Remove")] if d.kind == 'review_projects' else None
    ui.choice = keep_unlisted
    send("read_hours", month="2026-09")
    review = [d for d in ui.decisions if d.kind == 'review_projects'][-1]
    assert any(o.startswith("Remove P200") for o in review.options)
    assert any(o.startswith("Add VIRT1") for o in review.options)
    assert any("P200 was closed" in t and "VIRT1 but it is not in your list" in t for t in ui.said)
    assert agent.store.my_projects() == ['P100']
    assert any("won't suggest them again" in t for t in ui.said)

    n = len(ui.decisions)
    send("read_hours", month="2026-09")
    assert not [d for d in ui.decisions[n:] if d.kind == 'review_projects']


def test_review_flags_projects_without_hours(env):
    agent, ui, pipe, send = env
    pipe.virtual = []
    agent.store.add_projects(['P300'])
    agent.store._run(lambda c: c.execute("UPDATE projects SET added = '2020-01-01'"))
    send("read_hours", month="2026-08")
    send("read_hours", month="2026-09")
    review = [d for d in ui.decisions if d.kind == 'review_projects'][-1]
    assert review.options == ["Remove P300 — Other  · no hours in 2026-08, 2026-09"]
    assert "P300" not in agent.store.my_projects()


def test_target_questions_after_reading(env):
    agent, ui, pipe, send = env
    send("read_hours", month="2026-09")
    assert "dedication to P100" in ui.said[-1]                  # VIRT1 se prorratea: no se pregunta
    agent.handle("30%")
    assert agent.store.targets()['P100']['pct'] == 30
    assert not agent.pending_targets and "You can also ask" in ui.said[-1]


def test_add_and_remove_projects_by_chat(env):
    agent, ui, pipe, send = env
    send("add_project", project="P300")
    assert "P300" in agent.store.my_projects() and "P300" in pipe.categories
    send("remove_project", project="P300")
    assert "P300" not in agent.store.my_projects()
    assert "Outlook categories are kept" in ui.said[-1]
    send("my_projects")
    assert ui.cards[-1][0] == "My projects (2)"


def _old_excel(tmp_path, codes):
    path = tmp_path / "old.xlsx"
    pd.DataFrame({'Code': codes, 'Include': [1] * len(codes)}).to_excel(
        path, sheet_name="N4W-Projects", index=False)
    return str(path)


def test_first_time_import_excel_with_file_picker(tmp_path, monkeypatch):
    saved = []
    monkeypatch.setattr(Settings, "save", lambda self: saved.append(self.db_path))
    ui, pipe = FakeUI(), FakePipe(tmp_path)
    agent = agent_mod.Agent(ui, Settings(), store=History(str(tmp_path / "h.db")))
    agent._pipeline = lambda: pipe
    agent.greet()
    assert "“import my Excel”" in ui.said[-1]
    assert agent.suggestions()[0] == "import my Excel"

    ui.file = None                                   # canceló el explorador → vuelve a preguntar
    agent.handle("import my Excel")
    assert ui.picked and agent.awaiting_codes and "which projects" in ui.said[-1]

    ui.file = _old_excel(tmp_path, ['P100', 'P300', 'XX01'])
    agent.handle("importar mi excel")               # sin LLM, sin tildes/mayúsculas
    assert agent.store.my_projects() == ['P100', 'P300']
    assert saved[-1] == ui.file                     # la ruta se recuerda
    assert not agent.awaiting_codes


def test_import_excel_unreadable_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, "save", lambda self: None)
    ui, pipe = FakeUI(), FakePipe(tmp_path)
    agent = agent_mod.Agent(ui, Settings(), store=History(str(tmp_path / "h.db")))
    agent._pipeline = lambda: pipe
    bad = tmp_path / "bad.xlsx"
    pd.DataFrame({'X': [1]}).to_excel(bad, index=False)
    ui.file = str(bad)
    monkeypatch.setattr(llm, "parse_intent", lambda t, h: _intent("import_projects"))
    agent.handle("import my projects from Excel")
    assert any("couldn't read bad.xlsx" in t for t in ui.said)
    assert "which projects" in ui.said[-1]


def test_workday_single_week_of_read_month(env):
    agent, ui, pipe, send = env
    pipe.virtual = []
    send("read_hours", month="2026-09")
    send("fill_workday", start_date="2026-09-09")                  # miércoles → semana del domingo 6
    assert pipe.weeks_only == ["2026-09-06"]
    assert pipe.approved[-1].startswith("Fill Workday week 2026-09-06")
    assert not agent.loaded.workday_done                           # el mes completo sigue pendiente


def test_workday_week_crossing_months_keeps_month_days(env):
    agent, ui, pipe, send = env
    pipe.virtual = []
    send("read_hours", month="2026-09")
    send("fill_workday", start_date="2026-09-29")                  # semana 27/09–03/10
    assert pipe.weeks_only == ["2026-09-27"]
    assert "2026-09-27 → 2026-09-30" in pipe.approved[-1]           # solo los días de septiembre


def test_workday_week_of_other_month_asks_to_read_it(env):
    agent, ui, pipe, send = env
    pipe.virtual = []
    send("read_hours", month="2026-09")
    pipe.filled = None
    assert send("fill_workday", start_date="2026-11-10").startswith("First read your hours")
    assert pipe.filled is None


def test_workday_blocks_hours_after_project_closed(env):
    agent, ui, pipe, send = env
    pipe.virtual = []
    pipe.status['P100']['closed'] = '2026-09-15'                    # cerró a mitad de mes
    send("read_hours", month="2026-09")                             # leer sí: queda para análisis
    assert agent.store.hours(*agent._period(_intent("x", month="2026-09"))[:2]).shape[0] > 0
    assert "P100" in send("fill_workday") and pipe.filled is None   # el mes tiene días posteriores
    assert any(t.startswith("⛔") for t, _ in ui.cards)
    send("fill_workday", start_date="2026-09-08")                   # semana antes del cierre: permitido
    assert pipe.weeks_only == ["2026-09-06"]


def test_analysis_comes_with_charts(env):
    agent, ui, pipe, send = env
    pipe.virtual = []
    send("read_hours", month="2026-08")
    send("read_hours", month="2026-09")
    send("hours_summary", month="2026-09")
    assert [c['kind'] for c in ui.charts[-2:]] == ['donut', 'daily']
    send("compare_months", month="2026-09", month2="2026-08")
    assert ui.charts[-1]['kind'] == 'grouped'
    send("show_chart", project="P100")
    assert ui.charts[-1]['kind'] == 'trend' and ui.charts[-1]['x'] == ['2026-08', '2026-09']
    send("show_chart")
    assert ui.charts[-1]['kind'] == 'stacked'


def test_add_project_reports_created_and_existing_categories(env):
    agent, ui, pipe, send = env
    agent.store.remove_projects(['P100', 'VIRT1'])
    agent.store.add_projects(['VIRT1'])
    pipe.outlook = {'P300'}                                         # P300 ya tiene categoría (otro nombre)
    agent.status = pipe.status
    agent._add_codes(['P100', 'P300', 'VIRT1'])
    said = " ".join(ui.said)
    assert "VIRT1" in pipe.categories                               # ya en la lista: igual se revisa
    assert "Created: P100" in said and "Already in Outlook (kept as they are): P300 | old name" in said


def test_categorize_meetings_suggests_and_assigns(env):
    agent, ui, pipe, send = env
    ui.choice = lambda d: {r['label']: r['default'] for r in d.context['rows'] if r['default']}
    send("categorize_meetings", month="2026-10")
    rows = ui.decisions[-1].context['rows']
    assert [r['default'] for r in rows] == ['P100', None]          # sugerido por el asunto en septiembre
    assert pipe.assigned == [('Weekly sync', 2, 'P100')]
    assert ui.said[-1].startswith("✓ 2 meetings categorized") and "(1 still without category)" in ui.said[-1]


def test_model_override_defaults_to_config(monkeypatch):
    from agent import llm
    import config
    llm.set_model("")
    assert llm.current_model() == config.OLLAMA_MODEL
    llm.set_model("qwen3:8b")
    assert llm.current_model() == "qwen3:8b"
    llm.set_model("")
    assert llm.current_model() == config.OLLAMA_MODEL
