# ============================================================
# ACOMPAÑANTE — Tributary en el escritorio con la app cerrada (opción "solo cuando hay aviso")
#   Arranca al iniciar Windows (acceso en Inicio: install.bat / ui/autostart.py) o al abrir
#   la app; una sola instancia.
#   Recordatorios de horas (core/reminders.py): lun–vie 9–18 y solo con la app cerrada.
#   Clic → abre la app (o la trae al frente); "Más tarde" → en una hora; ✕ → hasta mañana.
#   Versión nueva: revisa GitHub al iniciar y cada 6 h (con internet); cualquier día de
#   8 a 20 ofrece instalarla. SOLO si el usuario pulsa "Actualizar": si la app está abierta
#   le pide cerrarla y sigue solo en cuanto la cierra; corre update.ps1 sin ventana, cuenta
#   cómo va y al terminar se reinicia con el código nuevo (si cambió environment.yml,
#   pide abrir la app: el lanzador recrea el ambiente).
#   Si el usuario apaga "Tributary on the desktop" en Settings, se cierra.
# Pruebas: python companion.py --demo          (aviso de fin de mes ya, a cualquier hora)
#          python companion.py --demo-update   (ofrece una versión ficticia; aceptar corre update.ps1)
# ============================================================
import os
import sys
import threading
import time
import traceback
import webbrowser
from datetime import date, datetime, timedelta

CHECK_MS = 5 * 60 * 1000       # sin aviso en pantalla
WATCH_MS = 3000                # con aviso: se esconde en cuanto el usuario abre la app
FIRST_CHECK_MS = 20 * 1000     # al iniciar Windows, dejar que el escritorio cargue
OFFLINE_RETRY = timedelta(minutes=30)   # sin internet: volver a mirar GitHub antes de 6 h
MUTEX = "TimeSheetAgent.Tributary"


def _log(text: str):
    home = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TimeSheetAgent")
    try:
        os.makedirs(home, exist_ok=True)
        with open(os.path.join(home, "companion.log"), "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}\n")
    except OSError:
        pass


class Companion:
    def __init__(self, root, demo: bool = False, demo_update: bool = False):
        import config
        from core import reminders
        from ui.floater import Floater
        self.root = root
        self.reminders = reminders
        self.home = config.APP_HOME
        self.db = config.HISTORY_DB
        self.seen = reminders.Seen(self.db)
        self.floater = Floater(root, root.winfo_fpixels("1i") / 96, self.seen, title="Tributary companion")
        self.current = None
        self.lang = "en"
        self.demo = demo
        self.demo_key = f"demo:{datetime.now():%Y%m%d%H%M%S}"
        self.update = None                         # Reminder de versión nueva (o None)
        self.checked_at = None                     # última consulta a GitHub
        self.mode = None                           # None | wait_close | updating | result
        if demo_update:
            self.update = reminders.Reminder("update:demo", "remind_update", {"version": "v9.9.9"})
            self.checked_at = datetime.now()
        root.after(1000 if (demo or demo_update) else FIRST_CHECK_MS, self.tick)

    def tr(self, key: str, **kw) -> str:
        from agent import i18n
        return i18n.tr(key, self.lang, **kw)

    # ── Bucle ────────────────────────────────────────────────

    def tick(self):
        try:
            self.check()
        except Exception:
            _log(traceback.format_exc())
        try:
            fast = self.floater.visible or self.mode
            self.root.after(WATCH_MS if fast else CHECK_MS, self.tick)
        except Exception:                          # raíz destruida (apagado o reinicio)
            pass

    def check(self):
        from agent.settings import Settings
        from ui import winapi
        settings = Settings.load()
        self.lang = settings.language or "en"
        if not settings.floater and self.mode != "updating":   # el usuario lo apagó en Settings
            self.root.destroy()
            return
        if self.mode == "wait_close":
            if not winapi.find_app():
                self.start_update()
            return
        if self.mode:                              # actualizando o mostrando el resultado
            return
        now = datetime.now()
        self.check_update(now)
        reminder = self.pick(now, settings)
        if reminder is None:
            self.hide()
            return
        if self.floater.visible and self.current and self.current.key == reminder.key:
            return
        self.current = reminder
        if reminder.msg == "remind_update":
            self.offer_update(reminder)
            return
        from ui.floater import reminder_text
        self.floater.show(reminder_text(reminder, self.lang), self.open_app, self.close,
                          [(f"⏰ {self.tr('floater_later')}", self.later, False)])

    def pick(self, now, settings):
        """Qué decir ahora: la versión nueva (aunque la app esté abierta) o un recordatorio de horas."""
        from ui import winapi
        r = self.reminders
        if self.update and r.in_update_hours(now) and not winapi.app_floater_visible():
            offer = self.seen.pending([self.update], now)
            if offer:
                return offer
        if winapi.find_app():                      # con la app abierta, avisa ella (minimizada)
            return None
        if self.demo:
            return self.seen.pending([r.Reminder(self.demo_key, "remind_month_end", {"month": now.date()})], now)
        if not r.in_hours(now):
            return None
        country = self.seen.get("country") or settings.country
        return self.seen.pending(r.due(now.date(), r.workday_days(self.db), country), now)

    def check_update(self, now: datetime):
        """Al iniciar y cada 6 h, en segundo plano (curl puede tardar unos segundos)."""
        r = self.reminders
        if self.checked_at and now - self.checked_at < r.UPDATE_EVERY:
            return
        self.checked_at = now
        installed = r.installed_version(self.home)
        if not installed:
            return                                 # desde el repo: sin versión instalada

        def work():
            latest = r.latest_version()
            if not latest:                         # sin internet: reintentar pronto
                self.checked_at = now - r.UPDATE_EVERY + OFFLINE_RETRY
                return
            self.update = r.update_reminder(installed, latest)
        threading.Thread(target=work, daemon=True).start()

    # ── Recordatorios de horas ───────────────────────────────

    def hide(self):
        if self.floater.visible:
            self.floater.hide()
        self.current = None

    def open_app(self):
        from ui import winapi
        if self.current:
            self.seen.mark(self.current.key, date.today())
        self.hide()
        if not winapi.bring_to_front(winapi.find_app()):
            self.launch_app()
        self.demo = False

    def launch_app(self):
        from ui import autostart
        launcher = os.path.join(autostart.CODE_DIR, "TimeSheet_Agent.bat")
        try:
            os.startfile(launcher)                 # el lanzador prepara todo y abre la app
        except (AttributeError, OSError):
            _log(f"Could not open {launcher}")

    def later(self):
        if self.current:
            self.seen.snooze(self.current.key, datetime.now())
        self.hide()

    def close(self):
        if self.current:
            self.seen.mark(self.current.key, date.today())
        self.hide()
        self.demo = False

    # ── Versión nueva: solo si el usuario acepta ─────────────

    def offer_update(self, reminder):
        version = reminder.kw["version"]
        self.floater.show(self.tr("remind_update", version=version), lambda: None, self.close, [
            (self.tr("update_btn"), self.accept_update, True),
            (f"⏰ {self.tr('floater_later')}", self.later, False),
            (self.tr("update_notes"), lambda: webbrowser.open(self.reminders.release_page(version)), False),
        ])

    def accept_update(self):
        from ui import winapi
        self.version = self.current.kw["version"] if self.current else ""
        if winapi.find_app():                      # con la app abierta no se puede cambiar app\
            self.mode = "wait_close"
            self.floater.show(self.tr("update_close_app"),
                              lambda: winapi.bring_to_front(winapi.find_app()), self.cancel_update)
            return
        self.start_update()

    def cancel_update(self):
        self.mode = None
        self.later()

    def start_update(self):
        self.mode = "updating"
        self.floater.set_busy(True)
        self.floater.show(self.tr("update_working", version=self.version), lambda: None, self.floater.hide)

        def work():
            if self.update and self.update.key == "update:demo":
                time.sleep(4)
                status, out = "current", "demo"
            else:
                status, out = self.reminders.run_update(self.home)
            self.root.after(0, lambda: self.update_finished(status, out))
        threading.Thread(target=work, daemon=True).start()

    def update_finished(self, status: str, out: str):
        from ui import winapi
        self.floater.set_busy(False)
        _log(f"update {self.version}: {status}\n{out}")
        if status == "busy" and winapi.find_app():     # la abrieron mientras tanto
            self.mode = "wait_close"
            self.floater.show(self.tr("update_close_app"),
                              lambda: winapi.bring_to_front(winapi.find_app()), self.cancel_update)
            return
        if status == "current":                    # ya estaba al día (p. ej. la actualizó el lanzador)
            self.update, self.mode = None, None
            self.hide()
            return
        self.mode = "result"
        if status != "updated":
            def dismiss():
                if self.current:
                    self.seen.snooze(self.current.key, datetime.now(), self.reminders.UPDATE_EVERY)
                self.mode = None
                self.hide()
            self.floater.show(self.tr("update_failed"), dismiss, dismiss)
            return
        self.update = None
        if self.reminders.env_changed(self.home):  # el lanzador recrea Python (y reinicia a Tributary)
            def open_and_finish():
                self.hide()
                self.launch_app()
            self.floater.show(self.tr("update_done_env", version=self.version), open_and_finish, self.restart,
                              [(self.tr("update_open_app"), open_and_finish, True)])
            return

        def open_and_restart():
            if not winapi.bring_to_front(winapi.find_app()):
                self.launch_app()
            self.restart()
        self.floater.show(self.tr("update_done", version=self.version), open_and_restart, self.restart,
                          [(self.tr("update_open_app"), open_and_restart, True)])

    def restart(self):
        """Vuelve a abrirse con el código nuevo (la instancia nueva espera a que esta suelte el mutex)."""
        from ui import autostart
        self.floater.hide()
        autostart.launch(force=True, args=["--restart"])
        self.root.after(200, self.root.destroy)


def main():
    from ui import winapi
    tries = 40 if "--restart" in sys.argv else 1    # tras actualizar: esperar a que cierre la anterior
    for _ in range(tries):
        if winapi.single_instance(MUTEX):
            break
        time.sleep(0.25)
    else:
        return
    winapi.dpi_aware()
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.title("TimeSheet Agent - Tributary")
    Companion(root, demo="--demo" in sys.argv, demo_update="--demo-update" in sys.argv)
    root.mainloop()


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        main()
    except Exception:
        _log(traceback.format_exc())
