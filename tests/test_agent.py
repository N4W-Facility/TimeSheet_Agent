"""Flujos y agente con LLM simulado (sin Ollama, Outlook ni navegador)."""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import workflows  # noqa: E402
from agent import agent as agent_mod  # noqa: E402
from agent import llm  # noqa: E402
from agent.settings import Settings  # noqa: E402
from pipeline import Callbacks, Cancelled, Pipeline  # noqa: E402


class FakeUI:
    def __init__(self, choice=None):
        self.said, self.logs, self.choice = [], [], choice

    def say(self, text): self.said.append(text)
    def log(self, text): self.logs.append(text)
    def decide(self, d): return self.choice(d) if self.choice else None
    def approve(self, title, detail): return True


def make_pipe(tmp_path, decide):
    return Pipeline(str(tmp_path / "db.xlsx"), callbacks=Callbacks(decide=decide))


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


def _intent(action, **kw):
    base = dict(action=action, month=None, start_date=None, end_date=None,
                prorate=False, language="es", reply="ok")
    base.update(kw)
    return llm.Intent(**base)


@pytest.fixture
def no_translate(monkeypatch):
    monkeypatch.setattr(llm, "localize", lambda text, lang: text)


def test_agent_help_needs_no_settings(monkeypatch, no_translate):
    monkeypatch.setattr(llm, "parse_intent", lambda t, h: _intent("help", reply="Puedo llenar Workday"))
    ui = FakeUI()
    agent_mod.Agent(ui, Settings()).handle("¿qué puedes hacer?")
    assert ui.said == ["Puedo llenar Workday"]


def test_agent_asks_for_settings(monkeypatch, no_translate):
    monkeypatch.setattr(llm, "parse_intent", lambda t, h: _intent("fill_workday", month="2026-10"))
    ui = FakeUI()
    agent_mod.Agent(ui, Settings()).handle("llena octubre")
    assert "Settings" in ui.said[-1]


def test_agent_asks_month_when_missing(monkeypatch, no_translate, tmp_path):
    db = tmp_path / "db.xlsx"
    db.write_bytes(b"")
    monkeypatch.setattr(llm, "parse_intent", lambda t, h: _intent("fill_workday"))
    ui = FakeUI()
    agent_mod.Agent(ui, Settings(db_path=str(db))).handle("llena workday")
    assert ui.said[-1].startswith("Which month?")


def test_agent_routes_workday_month(monkeypatch, no_translate, tmp_path):
    db = tmp_path / "db.xlsx"
    db.write_bytes(b"")
    calls = []
    monkeypatch.setattr(llm, "parse_intent", lambda t, h: _intent("fill_workday", month="2026-10", prorate=True))
    monkeypatch.setattr(workflows, "run_workday_month",
                        lambda pipe, y, m, use_prorate: calls.append((y, m, use_prorate)))
    ui = FakeUI()
    agent_mod.Agent(ui, Settings(db_path=str(db))).handle("fill october with prorate")
    assert calls == [(2026, 10, True)]
    assert ui.said[-1].startswith("✓ Workday filled for October 2026")
