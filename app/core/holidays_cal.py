# ============================================================
# FESTIVOS DEL PAÍS — para avisar de días festivos sin licencia
# País: región de Windows (Configuración → Hora e idioma → Región).
# Festivos: librería `holidays` (sin red). Sin ella no hay avisos.
# La fuente definitiva es Workday (marca el festivo en la cabecera
# del día); esto avisa antes, al leer Outlook.
# ============================================================
import locale
import logging
from datetime import datetime
from typing import Dict, List, Tuple

import pandas as pd

from core.utils import is_special_code

log = logging.getLogger(__name__)


def detect_country() -> str:
    """Código ISO de 2 letras del país del equipo ('CO', 'US'...) o '' si no se sabe."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\International\Geo") as key:
            name = str(winreg.QueryValueEx(key, "Name")[0]).strip().upper()
            if len(name) == 2 and name.isalpha():
                return name
    except Exception:
        pass
    try:
        loc = locale.getlocale()[0] or ""          # 'es_CO' / 'Spanish_Colombia'
        region = loc.replace('-', '_').split('_')[-1].split('.')[0]
        if len(region) == 2 and region.isalpha():
            return region.upper()
    except Exception:
        pass
    return ""


def public_holidays(country: str, start: datetime, end: datetime) -> Dict[str, str]:
    """Festivos lunes–viernes de [start, end]: {'YYYY-MM-DD': nombre}. {} si no se puede saber."""
    if not country:
        return {}
    try:
        import holidays
        cal = holidays.country_holidays(country, years=range(start.year, end.year + 1))
    except Exception as e:                         # sin librería o país no soportado
        log.info(f"No holiday calendar for '{country}': {e}")
        return {}
    return {d.strftime('%Y-%m-%d'): name for d, name in sorted(cal.items())
            if start.date() <= d <= end.date() and d.weekday() < 5}


def missing_absences(df: pd.DataFrame, holidays: Dict[str, str]) -> List[Tuple[str, str]]:
    """Festivos sin ninguna licencia (XX) ese día. df en formato largo (analysis.to_long)."""
    absent = set(df.loc[df['code'].map(is_special_code), 'day']) if not df.empty else set()
    return [(day, name) for day, name in holidays.items() if day not in absent]
