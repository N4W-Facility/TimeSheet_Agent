"""Tests de los recordatorios de Tributary en el escritorio (sin abrir ventanas)."""
import json
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import settings as settings_mod  # noqa: E402
from core import reminders  # noqa: E402
from core.history import History  # noqa: E402
from ui.floater import reminder_text  # noqa: E402


def test_business_days_skip_weekends_and_country_holidays():
    days = reminders.business_days(2026, 10, "CO")
    assert date(2026, 10, 12) not in days            # festivo en Colombia (lunes)
    assert date(2026, 10, 10) not in days            # sábado
    assert days[-1] == date(2026, 10, 30)            # el 31 es sábado
    assert date(2026, 10, 12) in reminders.business_days(2026, 10, "")


def test_month_end_only_on_last_business_day_and_until_workday_is_filled():
    last = date(2026, 10, 30)
    [r] = reminders.due(last, set(), "CO")
    assert (r.key, r.msg, r.kw["month"]) == ("month_end:2026-10", "remind_month_end", last)
    assert reminders.due(date(2026, 10, 29), set(), "CO") == []
    filled = set(reminders.business_days(2026, 10, "CO"))
    assert reminders.due(last, filled, "CO") == []


def test_previous_month_is_reminded_in_the_first_business_days():
    # noviembre 2026 en Colombia: el lunes 2 es festivo → hábiles 3, 4, 5…
    for d in (3, 4, 5):
        [r] = reminders.due(date(2026, 11, d), set(), "CO")
        assert r.key == "prev_month:2026-10"
    assert reminders.due(date(2026, 11, 6), set(), "CO") == []
    october = set(reminders.business_days(2026, 10, "CO"))
    assert reminders.due(date(2026, 11, 3), october, "CO") == []


def test_workday_days_come_from_month_and_week_events(tmp_path):
    db = str(tmp_path / "h.db")
    store = History(db)
    store.log_event("2026-10-01", "2026-10-03", "workday")
    store.log_event("2026-10-04", "2026-10-31", "workday")
    store.log_event("2026-09-01", "2026-09-30", "read")
    days = reminders.workday_days(db)
    assert date(2026, 10, 1) in days and date(2026, 10, 31) in days
    assert date(2026, 9, 15) not in days
    assert reminders.month_filled(2026, 10, days, "CO")
    assert reminders.workday_days(str(tmp_path / "missing.db")) == set()


def test_each_reminder_once_a_day_and_snooze_one_hour(tmp_path):
    db = str(tmp_path / "h.db")
    History(db)
    seen = reminders.Seen(db)
    r = reminders.Reminder("month_end:2026-10", "remind_month_end", {"month": date(2026, 10, 30)})
    now = datetime(2026, 10, 30, 10, 0)
    assert seen.pending([r], now) is r
    seen.snooze(r.key, now)
    assert seen.pending([r], datetime(2026, 10, 30, 10, 30)) is None
    assert seen.pending([r], datetime(2026, 10, 30, 11, 1)) is r
    seen.mark(r.key, now.date())
    assert seen.pending([r], datetime(2026, 10, 30, 15, 0)) is None
    assert seen.pending([r], datetime(2026, 10, 31, 9, 0)) is r          # otro día vuelve
    seen.put("floater_pos", "1900,1000")
    assert seen.get("floater_pos") == "1900,1000"
    # comparte la tabla profile con el historial (país base)
    History(db).set_profile("country", "CO")
    assert seen.get("country") == "CO"


def test_seen_works_without_a_history_yet(tmp_path):
    seen = reminders.Seen(str(tmp_path / "new.db"))
    assert seen.get("floater_pos") == ""
    with sqlite3.connect(str(tmp_path / "new.db")) as c:
        assert c.execute("SELECT count(*) FROM profile").fetchone() == (0,)


def test_working_hours_are_weekdays_from_9_to_18():
    assert reminders.in_hours(datetime(2026, 10, 30, 9, 0))
    assert not reminders.in_hours(datetime(2026, 10, 30, 8, 59))
    assert not reminders.in_hours(datetime(2026, 10, 30, 18, 0))
    assert not reminders.in_hours(datetime(2026, 10, 31, 11, 0))         # sábado


def test_update_reminder_only_for_a_newer_installed_release():
    r = reminders.update_reminder("v1.2.0", "v1.3.0")
    assert (r.key, r.kw) == ("update:v1.3.0", {"version": "v1.3.0"})
    assert reminders.update_reminder("1.3.0", "v1.3.0") is None
    assert reminders.update_reminder("local", "v1.3.0") is None
    assert reminders.update_reminder("v1.2.0", "") is None


def test_reminder_texts_in_the_user_language():
    r = reminders.Reminder("month_end:2026-10", "remind_month_end", {"month": date.today()})
    assert "último día hábil" in reminder_text(r, "es")
    prev = reminders.Reminder("prev_month:x", "remind_prev_month", {"month": date(date.today().year, 1, 1)})
    assert reminder_text(prev, "es").startswith("Enero todavía no está en Workday")
    assert reminder_text(prev, "en").startswith("January")
    assert "1.3" in reminder_text(reminders.Reminder("u", "remind_update", {"version": "v1.3"}), "pt")


def test_floater_setting_defaults_on_and_persists(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_mod, "SETTINGS_PATH", str(path))
    monkeypatch.setattr(settings_mod, "APP_HOME", str(tmp_path))
    path.write_text(json.dumps({"email": "me@tnc.org"}), encoding="utf-8")
    assert settings_mod.Settings.load().floater is True
    s = settings_mod.Settings.load()
    s.floater = False
    s.save()
    assert settings_mod.Settings.load().floater is False


def test_update_is_offered_any_day_from_8_to_20():
    assert reminders.in_update_hours(datetime(2026, 10, 31, 8, 0))       # sábado también
    assert not reminders.in_update_hours(datetime(2026, 10, 31, 20, 0))
    assert not reminders.in_update_hours(datetime(2026, 10, 30, 7, 59))


def test_update_status_from_update_ps1_output():
    assert reminders.update_status("     New version v1.3 - downloading...\n     Updated to v1.3.") == "updated"
    assert reminders.update_status("     Up to date (v1.3).") == "current"
    assert reminders.update_status("     TimeSheet Agent is open - close it to update. Using the current version.") == "busy"
    assert reminders.update_status("     Could not check for updates (no connection to GitHub).") == "failed"
    assert reminders.update_status("") == "failed"


def test_env_changed_compares_environment_hash_like_the_launcher(tmp_path):
    import hashlib
    (tmp_path / "app").mkdir()
    yml = tmp_path / "app" / "environment.yml"
    yml.write_bytes(b"name: timesheet-agent\n")
    stamp = tmp_path / "mamba" / "envs" / "timesheet-agent" / ".environment.sha256"
    assert reminders.env_changed(str(tmp_path))                        # sin ambiente: hay que crearlo
    stamp.parent.mkdir(parents=True)
    stamp.write_text(hashlib.sha256(yml.read_bytes()).hexdigest().upper() + " \r\n")   # como `echo` de cmd
    assert not reminders.env_changed(str(tmp_path))
    yml.write_bytes(b"name: timesheet-agent\ndependencies: [pandas]\n")
    assert reminders.env_changed(str(tmp_path))


def test_failed_update_waits_six_hours(tmp_path):
    seen = reminders.Seen(str(tmp_path / "h.db"))
    r = reminders.update_reminder("v1.2", "v1.3")
    now = datetime(2026, 10, 31, 9, 0)
    seen.snooze(r.key, now, reminders.UPDATE_EVERY)
    assert seen.pending([r], datetime(2026, 10, 31, 14, 59)) is None
    assert seen.pending([r], datetime(2026, 10, 31, 15, 1)) is r


def test_release_page_and_installed_version(tmp_path):
    assert reminders.release_page("v1.3") == "https://github.com/N4W-Facility/TimeSheet_Agent/releases/tag/v1.3"
    assert reminders.installed_version(str(tmp_path)) == ""
    (tmp_path / "version.txt").write_text("v1.2.1", encoding="utf-8")
    assert reminders.installed_version(str(tmp_path)) == "v1.2.1"
