# ============================================================
# LANZADOR DE CHROME CON DEPURACIÓN REMOTA
# ============================================================
import subprocess
import sys
import os
import time
import socket
import getpass
import requests
from config import CDP_PORT, CDP_URL, WORKDAY_HOME_URL, CHROME_PATHS
def find_chrome_path() -> str:
    """
    Detecta automáticamente la ruta de Chrome según el sistema operativo.
    Retorna la ruta si la encuentra, o None si no.
    """
    platform = sys.platform
    paths = CHROME_PATHS.get(platform, [])
    for path in paths:
        # Reemplazar {username} si existe en la ruta (Windows)
        path = path.replace("{username}", getpass.getuser())
        if os.path.exists(path):
            return path
    return None
def is_cdp_running() -> bool:
    """
    Verifica si ya hay un Chrome con CDP corriendo en el puerto configurado.
    """
    try:
        resp = requests.get(f"{CDP_URL}/json/version", timeout=2)
        return resp.status_code == 200
    except Exception:
        return False
def launch_chrome(log_callback=None) -> bool:
    """
    Lanza Chrome con depuración remota y abre Workday.
    Retorna True si lo logró, False si no encontró Chrome.
    """
    log = log_callback if log_callback else print
    # Si ya hay CDP corriendo, no lanzar otro
    if is_cdp_running():
        log("✓ Chrome con depuración remota ya está activo")
        return True
    # Buscar Chrome
    chrome_path = find_chrome_path()
    if not chrome_path:
        log("✗ No se encontró Chrome. Instálalo o agrega la ruta manualmente en config.py")
        return False
    log(f"✓ Chrome encontrado: {chrome_path}")
    log("Lanzando Chrome con depuración remota...")
    # Carpeta de perfil temporal para no interferir con el perfil normal
    user_data_dir = os.path.join(os.path.expanduser("~"), ".workday_automation_profile")
    os.makedirs(user_data_dir, exist_ok=True)
    # Comando para lanzar Chrome
    cmd = [
        chrome_path,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        WORKDAY_HOME_URL,  # Abre Workday directamente
    ]
    # Lanzar en background
    if sys.platform == "win32":
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Esperar a que CDP esté listo (máximo 15 segundos)
    log("Esperando que Chrome inicie...")
    for i in range(15):
        time.sleep(1)
        if is_cdp_running():
            log(f"✓ Chrome listo (tardó {i+1}s)")
            return True
    log("✗ Chrome no respondió a tiempo. Inténtalo manualmente.")
    return False