# ============================================================
# PUNTO DE ENTRADA — interfaz de chat
#   Usuarios: doble clic en TimeSheet_Agent.bat (lanza con pythonw, sin consola)
#   Desarrollo: python app.py
# Con pythonw no hay consola: un error al arrancar se muestra en una
# ventana y se guarda en %LOCALAPPDATA%\TimeSheetAgent\app.log.
# ============================================================
import os
import traceback


def _report_fatal(error: str):
    log_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TimeSheetAgent")
    try:
        os.makedirs(log_dir, exist_ok=True)
        with open(os.path.join(log_dir, "app.log"), "a", encoding="utf-8") as f:
            f.write(error + "\n")
    except OSError:
        pass
    try:
        from tkinter import Tk, messagebox
        root = Tk()
        root.withdraw()
        messagebox.showerror("TimeSheet Agent", f"The application could not start:\n\n{error[-1500:]}")
        root.destroy()
    except Exception:
        print(error)


if __name__ == "__main__":
    try:
        from ui.chat_app import main
        main()
    except Exception:
        _report_fatal(traceback.format_exc())
