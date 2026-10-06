# ============================================================
# AJUSTES DEL USUARIO (settings.json junto a la app)
# ============================================================
import json
import os
from dataclasses import asdict, dataclass

SETTINGS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "settings.json")


@dataclass
class Settings:
    db_path: str = ""
    email: str = ""

    @classmethod
    def load(cls) -> "Settings":
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return cls(**{k: data.get(k, "") for k in ("db_path", "email")})
        except (OSError, ValueError):
            return cls()

    def save(self):
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)

    def missing(self, need_email: bool = False) -> list:
        out = []
        if not self.db_path or not os.path.exists(self.db_path):
            out.append("the projects database")
        if need_email and not self.email:
            out.append("your email")
        return out
