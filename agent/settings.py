# ============================================================
# AJUSTES DEL USUARIO (settings.json junto a la app)
# ============================================================
import json
import os
from dataclasses import asdict, dataclass

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")


@dataclass
class Settings:
    email: str = ""
    db_path: str = ""       # Excel de proyectos antiguo: solo para importar sus códigos una vez
    language: str = ""      # último idioma del usuario (saludo y sugerencias)

    @classmethod
    def load(cls) -> "Settings":
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return cls(**{k: data.get(k, "") for k in ("db_path", "email", "language")})
        except (OSError, ValueError):
            return cls()

    def save(self):
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    def missing(self) -> list:
        """Datos sin los que la app no arranca (el email: Outlook y N4W)."""
        return [] if self.email else ["your email"]

    def legacy_db(self) -> str:
        return self.db_path if self.db_path and os.path.exists(self.db_path) else ""
