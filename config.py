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
REPORT_NAME = "01-Report.xlsx"
TIMESHEET_NAME = "02-Timesheet.csv"
PRORATE_NAME = "03-Timesheet_Prorate.csv"

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

# ── Ollama (fase 3) — configurable para servidor compartido ──
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_NUM_CTX = 8192
