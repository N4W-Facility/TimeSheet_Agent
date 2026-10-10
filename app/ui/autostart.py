# ============================================================
# ACOMPAÑANTE AL INICIAR WINDOWS — acceso directo en la carpeta Inicio del usuario
# (sin permisos de administrador) que abre companion.py con el pythonw del ambiente.
# Lo crea/quita la app según el ajuste "Tributary on the desktop": así también lo
# reciben quienes se actualizaron sin volver a correr install.bat.
# Solo en la copia instalada (%LOCALAPPDATA%\TimeSheetAgent\app); desde el repo no.
# ============================================================
import os
import subprocess
import sys

APP_HOME = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TimeSheetAgent")
CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPANION = os.path.join(CODE_DIR, "companion.py")
LINK_NAME = "TimeSheet Agent - Tributary.lnk"


def installed() -> bool:
    return os.path.normcase(CODE_DIR) == os.path.normcase(os.path.join(APP_HOME, "app"))


def pythonw() -> str:
    """pythonw.exe junto al python que corre la app (sin ventana de consola)."""
    exe = sys.executable
    candidate = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return candidate if os.path.exists(candidate) else exe


def link_path() -> str:
    startup = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                           "Start Menu", "Programs", "Startup")
    return os.path.join(startup, LINK_NAME)


def sync(enabled: bool):
    """Crea o quita el acceso directo de Inicio. Nunca rompe la app."""
    if sys.platform != "win32" or not installed():
        return
    path = link_path()
    try:
        if not enabled:
            if os.path.exists(path):
                os.remove(path)
            return
        import win32com.client
        link = win32com.client.Dispatch("WScript.Shell").CreateShortcut(path)
        link.TargetPath = pythonw()
        link.Arguments = f'"{COMPANION}"'
        link.WorkingDirectory = APP_HOME            # fuera de app\: la actualización puede reemplazarla
        link.IconLocation = os.path.join(CODE_DIR, "ui", "icon.ico")
        link.Description = "TimeSheet Agent - Tributary reminders"
        link.Save()
    except Exception:
        pass


def launch(force: bool = False, args=()):
    """Abre el acompañante (si ya corre, la instancia nueva se cierra sola)."""
    if sys.platform != "win32" or not (installed() or force):
        return
    flags = 0x00000008 | 0x00000200                 # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        subprocess.Popen([pythonw(), COMPANION, *args], cwd=APP_HOME if os.path.isdir(APP_HOME) else CODE_DIR,
                         creationflags=flags, close_fds=True)
    except OSError:
        pass
