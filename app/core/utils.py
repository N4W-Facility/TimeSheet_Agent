import re
from datetime import datetime


def get_date_columns(df) -> list:
    """Columnas cuyo nombre contiene una fecha YYYY-MM-DD."""
    date_pattern = re.compile(r'\d{4}-\d{2}-\d{2}')
    return [col for col in df.columns if date_pattern.search(str(col))]


def remove_timezone(date: datetime) -> datetime:
    return date.replace(tzinfo=None)


def is_special_code(code) -> bool:
    """Códigos 'XX...' no se actualizan, no se prorratean y en N4W se reportan como OF0104."""
    return str(code).strip().upper().startswith('XX')
