# ============================================================
# FESTIVOS DEL PAÍS — para avisar de días festivos sin licencia
# País: región de Windows (Configuración → Hora e idioma → Región).
# Festivos: librería `holidays` (sin red). Sin ella no hay avisos.
# La fuente definitiva es Workday (marca el festivo en la cabecera
# del día); esto avisa antes, al leer Outlook.
# ============================================================
import locale
import logging
import re
import unicodedata
from datetime import datetime
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

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


# Nombres en español/portugués de los países más probables (la lista viene en inglés)
ALIASES = {
    "CO": "colombia", "US": "estados unidos eeuu usa estados unidos da america", "BR": "brasil",
    "MX": "mexico", "PE": "peru", "EC": "ecuador", "CL": "chile", "AR": "argentina",
    "BO": "bolivia", "PY": "paraguai", "UY": "uruguai", "VE": "venezuela", "PA": "panama",
    "CR": "costa rica", "GT": "guatemala", "HN": "honduras", "SV": "el salvador", "NI": "nicaragua",
    "DO": "republica dominicana", "PR": "porto rico", "CA": "canada", "GB": "reino unido inglaterra",
    "ES": "espana espanha", "PT": "portugal", "FR": "francia franca", "DE": "alemania alemanha",
    "IT": "italia", "NL": "paises bajos holanda paises baixos", "BE": "belgica", "CH": "suiza suica",
    "KE": "kenia quenia", "ZA": "sudafrica africa do sul", "TZ": "tanzania", "CN": "china",
    "JP": "japon japao", "IN": "india", "ID": "indonesia", "AU": "australia", "NZ": "nueva zelanda nova zelandia",
    "PH": "filipinas", "SG": "singapur singapura",
}
_FALLBACK = {"CO": "Colombia", "US": "United States", "BR": "Brazil", "MX": "Mexico", "PE": "Peru",
             "EC": "Ecuador", "CL": "Chile", "AR": "Argentina", "CA": "Canada", "GB": "United Kingdom",
             "ES": "Spain", "KE": "Kenya", "AU": "Australia"}


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.lower()) if not unicodedata.combining(c))


@lru_cache(maxsize=1)
def countries() -> Dict[str, str]:
    """{'CO': 'Colombia', ...}: los países con calendario de festivos, ordenados por nombre."""
    try:
        from holidays import registry
        names = {v[1]: k.replace('_', ' ').title().replace(' And ', ' and ').replace(' Of ', ' of ')
                 for k, v in registry.COUNTRIES.items()}
    except Exception:                              # sin librería: los más probables
        names = dict(_FALLBACK)
    return dict(sorted(names.items(), key=lambda kv: kv[1]))


def country_name(code: str) -> str:
    return countries().get((code or "").upper(), code or "")


def search_countries(query: str, limit: int = 8) -> List[str]:
    """Códigos cuyo nombre (inglés, español o portugués) o código coincide con lo escrito."""
    q = _plain(query).strip()
    if not q:
        return list(countries())[:limit]
    starts, inside = [], []
    for code, name in countries().items():
        words = f"{_plain(name)} {ALIASES.get(code, '')}"
        if q == code.lower() or re.search(rf"\b{re.escape(q)}", words):
            starts.append(code)
        elif q in words:
            inside.append(code)
    return (starts + inside)[:limit]


def find_country(text: str) -> Optional[str]:
    """País nombrado en un mensaje ("cambia mi país a Brasil") o None."""
    plain = f" {_plain(text)} "
    for code, name in sorted(countries().items(), key=lambda kv: -len(kv[1])):
        for alias in [_plain(name)] + [a for a in re.split(r"\s{2,}|,", ALIASES.get(code, "")) if a]:
            if re.search(rf"\b{re.escape(alias.strip())}\b", plain):
                return code
    for alias_code, words in ALIASES.items():          # alias de una palabra ("brasil", "espana")
        for w in words.split():
            if len(w) > 3 and re.search(rf"\b{w}\b", plain):
                return alias_code
    return None


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
