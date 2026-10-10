# ============================================================
# WINDOWS (ctypes) — lo mínimo para que Tributary viva en el escritorio:
#   ventana de la app (¿está abierta? traerla al frente), una sola instancia
#   del acompañante y el área de trabajo (pantalla sin la barra de tareas).
# En otros sistemas (tests en WSL) todo devuelve un valor neutro.
# ============================================================
import sys

APP_TITLE = "TimeSheet Agent"     # título de la ventana principal (chat_app)
FLOATER_TITLE = "Tributary"       # Tributary de la app minimizada (ui/floater.py)
_TK_CLASS = "TkTopLevel"          # clase de las ventanas raíz de Tk en Windows
_SW_RESTORE = 9
_SPI_GETWORKAREA = 48
_ERROR_ALREADY_EXISTS = 183

WINDOWS = sys.platform == "win32"
_mutexes = []                     # referencias vivas: el mutex dura lo que el proceso


def _user32():
    import ctypes
    return ctypes.windll.user32


def dpi_aware():
    """Coordenadas en píxeles reales (como CustomTkinter): sin esto Windows estira la ventana borrosa."""
    if not WINDOWS:
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            _user32().SetProcessDPIAware()
        except Exception:
            pass


def single_instance(name: str) -> bool:
    """True si este proceso es el único con ese nombre (mutex con nombre de Windows)."""
    if not WINDOWS:
        return True
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, f"Local\\{name}")
    if handle and ctypes.get_last_error() == _ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(ctypes.c_void_p(handle))   # no retenerlo: si no, el mutex no muere con el otro
        return False
    if not handle:
        return False
    _mutexes.append(handle)
    return True


def find_app() -> int:
    """Ventana principal de TimeSheet Agent (0 si la app no está abierta)."""
    if not WINDOWS:
        return 0
    try:
        return _user32().FindWindowW(_TK_CLASS, APP_TITLE) or 0
    except Exception:
        return 0


def app_floater_visible() -> bool:
    """¿La app minimizada ya muestra su Tributary? (el acompañante no pone un segundo)."""
    if not WINDOWS:
        return False
    try:
        user32 = _user32()
        hwnd = user32.FindWindowW(_TK_CLASS, FLOATER_TITLE)
        return bool(hwnd and user32.IsWindowVisible(hwnd))
    except Exception:
        return False


def bring_to_front(hwnd: int) -> bool:
    """Restaura (si está minimizada) y trae al frente la ventana."""
    if not (WINDOWS and hwnd):
        return False
    user32 = _user32()
    try:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, _SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        return True
    except Exception:
        return False


def work_area(root):
    """(izq, arriba, der, abajo) del monitor principal sin la barra de tareas."""
    if WINDOWS:
        import ctypes
        from ctypes import wintypes
        rect = wintypes.RECT()
        try:
            if _user32().SystemParametersInfoW(_SPI_GETWORKAREA, 0, ctypes.byref(rect), 0):
                return rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight() - 48


def virtual_screen(root):
    """(izq, arriba, der, abajo) de todos los monitores juntos: una posición guardada debe caer dentro."""
    if WINDOWS:
        try:
            u = _user32()
            x, y = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
            return x, y, x + u.GetSystemMetrics(78), y + u.GetSystemMetrics(79)
        except Exception:
            pass
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()
