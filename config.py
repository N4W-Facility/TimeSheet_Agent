# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================
import os

# ── Base de datos de códigos N4W (Box) ───────────────────────
BOX_URL = "https://tnc.box.com/s/6y6iswltvf26pxrk3rt1e5s2i7xfo7k4"
N4W_TASK_DETAILS_NAME = "N4W_Task_Details.xlsx"   # Se descarga junto a la BD del usuario
DB_SHEET = "N4W-Projects"
DB_PASSWORD = "TimeSheet_N4W"

# ── Archivos generados (en la carpeta de la BD del usuario) ──
# {start}/{end} = YYYY-MM-DD → cada periodo tiene sus propios archivos
REPORT_NAME = "01-Report_{start}_{end}.xlsx"
TIMESHEET_NAME = "02-Timesheet_{start}_{end}.csv"
PRORATE_NAME = "03-Timesheet_Prorate_{start}_{end}.csv"

# ── N4W Facility (OneDrive) ──────────────────────────────────
N4W_ONEDRIVE_FOLDER = "N4WTimeTracking - Science Timesheets"
ONEDRIVE_ACCOUNT_HINT = "The Nature Conservancy"

# ── Workday ──────────────────────────────────────────────────
WORKDAY_HOME_URL = "https://wd108.myworkday.com/nature/d/home.htmld"
TIMEOUT = 30000        # ms
MAX_RETRIES = 3
CDP_PORT = 9222
CDP_URL = f"http://localhost:{CDP_PORT}"
CHROME_PATHS = {
    "win32": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Users\{username}\AppData\Local\Google\Chrome\Application\chrome.exe",
    ],
    "darwin": ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"],
    "linux": ["/usr/bin/google-chrome", "/usr/bin/chromium-browser", "/usr/bin/chromium"],
}

# ── Ollama — configurable para servidor compartido ──
# Variables propias (no OLLAMA_HOST: en el servidor suele valer 0.0.0.0, que no sirve como cliente)
OLLAMA_HOST = os.environ.get("TSA_OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("TSA_OLLAMA_MODEL", "qwen3:8b")
OLLAMA_NUM_CTX = 8192
