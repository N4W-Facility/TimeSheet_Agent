# ============================================================
# CONFIGURACIÓN GENERAL
# ============================================================
import os

# ── Base de datos de códigos N4W (Box) ───────────────────────
BOX_URL = "https://tnc.box.com/s/6y6iswltvf26pxrk3rt1e5s2i7xfo7k4"
N4W_TASK_DETAILS_NAME = "N4W_Task_Details.xlsx"   # base global: se descarga al abrir la app
LEGACY_DB_SHEET = "N4W-Projects"   # Excel de proyectos antiguo: solo para importar los códigos una vez

# Códigos internos (licencias): no están en N4W_Task_Details, existen para todos
INTERNAL_CODES = {
    "XX01": "Maternity Leave", "XX02": "Administrative Leave Discretionary",
    "XX03": "Parental Leave", "XX04": "Compensation", "XX05": "Public Holiday",
    "XX06": "Medical Leave", "XX07": "TNC Personal Days Leave", "XX08": "Sick (Days)",
    "XX09": "Vacation (Days)",
}

# ── Archivos generados (carpeta de trabajo) ──────────────────
WORK_DIR = os.environ.get("TSA_WORK_DIR",
                          os.path.join(os.path.expanduser("~"), "Documents", "TimeSheetAgent"))
# {start}/{end} = YYYY-MM-DD → cada periodo tiene sus propios archivos
REPORT_NAME = "01-Report_{start}_{end}.xlsx"
TIMESHEET_NAME = "02-Timesheet_{start}_{end}.csv"
PRORATE_NAME = "03-Timesheet_Prorate_{start}_{end}.csv"

# ── N4W Facility (OneDrive) ──────────────────────────────────
N4W_ONEDRIVE_FOLDER = "N4WTimeTracking - Science Timesheets"
ONEDRIVE_ACCOUNT_HINT = "The Nature Conservancy"

# ── Workday ──────────────────────────────────────────────────
WORKDAY_HOME_URL = "https://wd108.myworkday.com/nature/d/home.htmld"
# Calendario "Introducción de horas": id de tarea fijo, igual en todos los idiomas
WORKDAY_TIME_CALENDAR_URL = "https://wd108.myworkday.com/nature/d/task/2997$4767.htmld"
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
# qwen3:4b: el LLM solo clasifica la frase → modelo liviano que corre aceptable sin GPU.
# Comparar modelos con: python eval_intents.py qwen3:1.7b qwen3:4b qwen3:8b
OLLAMA_MODEL = os.environ.get("TSA_OLLAMA_MODEL", "qwen3:4b")
OLLAMA_NUM_CTX = 4096

# ── Historial y análisis (memoria mes a mes) ─────────────────
APP_HOME = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TimeSheetAgent")
HISTORY_DB = os.path.join(APP_HOME, "history.db")   # SQLite: horas por día/código, objetivos, eventos
EXPECTED_DAILY_HOURS = 8.0      # lun–vie (no considera festivos)
ALERT_TARGET_TOLERANCE = 10.0   # puntos % (o % del objetivo en horas) antes de alertar
ALERT_AVERAGE_DEVIATION = 15.0  # puntos % frente al promedio histórico (proyectos sin objetivo)
TARGET_QUESTIONS_MAX = 3          # objetivos que se preguntan tras leer un mes
REVIEW_IDLE_MONTHS = 2          # meses seguidos sin horas → proponer quitar el proyecto
REVIEW_SNOOZE_DAYS = 30         # una propuesta rechazada no se repite antes de N días
HISTORY_DEFAULT_MONTHS = 6      # meses que carga "load my history" si no se indica
