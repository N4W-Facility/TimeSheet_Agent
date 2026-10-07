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
    "XX09": "Vacation (Days)", "XX10": "Parental Leave (Not TNC Funded)",
    "XX11": "Administrative Leave Legally Required", "XX12": "Administrative Leave Mandatory",
    "XX13": "Bereavement Leave", "XX14": "Leave Without Pay (LWOP)",
}
# Un día de licencia es completo: el usuario lo registra en Outlook como bloque de 8 h
# (N4W lo reporta así, como OF0104) y Workday recibe 1 (unidad = día).
# En Workday los XX van en "Tipo de jornada" → submenú Ausencia y se eligen por id
# (igual en todos los idiomas). XX01 y XX04 no aparecen en el menú (¿dependen del país?).
WORKDAY_ABSENCE_MENU_ID = "45$17777"
WORKDAY_ABSENCE_IDS = {
    "XX02": "2031$46", "XX03": "2031$168", "XX05": "2031$195", "XX06": "2031$43",
    "XX07": "2031$135", "XX08": "2031$196", "XX09": "2031$61", "XX10": "2031$34",
    "XX11": "2031$107", "XX12": "2031$128", "XX13": "2031$194", "XX14": "2031$182",
}
PUBLIC_HOLIDAY_CODE = "XX05"

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
# Fijo durante la sesión: si cambia entre llamadas, Ollama recarga el modelo.
# Una frase usa ~800 tokens; el resto del contexto es historial del chat.
OLLAMA_NUM_CTX = int(os.environ.get("TSA_OLLAMA_NUM_CTX", "4096"))
OLLAMA_CTX_BUDGET = 0.75       # el historial se recorta para no pasar de esta fracción
OLLAMA_MAX_HISTORY = int(os.environ.get("TSA_OLLAMA_MAX_HISTORY", "20"))   # mensajes; un modelo chico se confunde con demasiado historial
# 0.1 y no 0: Qwen3 desaconseja decodificación 100% greedy (repeticiones); poco azar = mismo intent
OLLAMA_TEMPERATURE = float(os.environ.get("TSA_OLLAMA_TEMPERATURE", "0.1"))
OLLAMA_NUM_PREDICT = 512       # tope de salida; el JSON ocupa ~150 tokens
OLLAMA_KEEP_ALIVE = "30m"      # modelo cargado en memoria entre mensajes
OLLAMA_TIMEOUT = 60            # segundos; si Ollama no responde, el agente avisa

# ── Historial y análisis (memoria mes a mes) ─────────────────
APP_HOME = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TimeSheetAgent")
HISTORY_DB = os.path.join(APP_HOME, "history.db")   # SQLite: horas por día/código, objetivos, eventos
CATEGORIZE_LOOKBACK_DAYS = 90    # historial de asuntos para sugerir el proyecto de una reunión
CATEGORIZE_MAX_ROWS = 15         # filas en la tarjeta de categorizar (las de más horas)
EXPECTED_DAILY_HOURS = 8.0      # lun–vie (no considera festivos)
ALERT_TARGET_TOLERANCE = 10.0   # puntos % (o % del objetivo en horas) antes de alertar
ALERT_AVERAGE_DEVIATION = 15.0  # puntos % frente al promedio histórico (proyectos sin objetivo)
TARGET_QUESTIONS_MAX = 3          # objetivos que se preguntan tras leer un mes
REVIEW_IDLE_MONTHS = 2          # meses seguidos sin horas → proponer quitar el proyecto
REVIEW_SNOOZE_DAYS = 30         # una propuesta rechazada no se repite antes de N días
HISTORY_DEFAULT_MONTHS = 6      # meses que carga "load my history" si no se indica
