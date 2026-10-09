# ============================================================
# AJUSTES DEL USUARIO (%LOCALAPPDATA%\TimeSheetAgent\settings.json)
#   Fuera de la carpeta del código: una actualización reemplaza app\ sin tocarlos.
# ============================================================
import json
import os
from dataclasses import asdict, dataclass

APP_HOME = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TimeSheetAgent")
SETTINGS_PATH = os.path.join(APP_HOME, "settings.json")
_CODE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# antes vivía junto al código (app\ o la raíz del repo): se migra la primera vez
LEGACY_PATHS = [os.path.join(_CODE_DIR, "settings.json"),
                os.path.join(os.path.dirname(_CODE_DIR), "settings.json")]


@dataclass
class Settings:
    email: str = ""
    db_path: str = ""       # Excel de proyectos antiguo: solo para importar sus códigos una vez
    language: str = ""      # último idioma del usuario (saludo y sugerencias)
    model: str = ""         # modelo Ollama elegido a mano; vacío → config.OLLAMA_MODEL
    country: str = ""       # ISO 2 letras (festivos); vacío → se detecta de Windows y se guarda
    avatar: bool = True     # personaje animado junto al chat

    @classmethod
    def load(cls) -> "Settings":
        path = SETTINGS_PATH if os.path.exists(SETTINGS_PATH) else \
            next((p for p in LEGACY_PATHS if os.path.exists(p)), SETTINGS_PATH)
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            settings = cls(**{k: data.get(k, "") for k in ("db_path", "email", "language", "model", "country")},
                           avatar=bool(data.get("avatar", True)))
        except (OSError, ValueError):
            return cls()
        if path != SETTINGS_PATH:
            try:
                settings.save()
            except OSError:
                pass
        return settings

    def save(self):
        os.makedirs(APP_HOME, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    def missing(self) -> list:
        """Datos sin los que la app no arranca (el email: Outlook y N4W)."""
        return [] if self.email else ["your email"]

    def legacy_db(self) -> str:
        return self.db_path if self.db_path and os.path.exists(self.db_path) else ""
