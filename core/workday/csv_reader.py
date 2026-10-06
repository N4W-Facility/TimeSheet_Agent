# ============================================================
# LECTURA Y AGRUPACIÓN DEL CSV POR SEMANAS
# ============================================================
import csv
from datetime import datetime, timedelta
from collections import defaultdict
def parse_csv(filepath: str) -> dict:
    """
    Lee el CSV y retorna un diccionario agrupado por semana.
    Solo incluye filas donde al menos un día tiene horas > 0.
    """
    # Detectar automáticamente el delimitador
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        sample = f.read(2048)
        f.seek(0)
        delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        rows = list(reader)

    if not rows:
        raise ValueError("El CSV está vacío o no se pudo leer correctamente.")

    # Detectar columnas de fecha — acepta DD-MM-YYYY, YYYY-MM-DD y YYYY-MM-DD HH:MM:SS
    DATE_FORMATS = ["%d-%m-%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
    fixed_cols = {"Code", "Task Name", "Grant ID"}

    def _parse_date_col(col: str):
        """Parsea la cabecera de columna como fecha. Retorna datetime o None."""
        s = col.strip()
        for fmt in DATE_FORMATS:
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None

    # Mapeo col_original → fecha normalizada DD-MM-YYYY
    date_columns = {}
    for col in rows[0].keys():
        if col.strip() in fixed_cols:
            continue
        dt = _parse_date_col(col)
        if dt:
            date_columns[col] = dt.strftime("%d-%m-%Y")

    if not date_columns:
        raise ValueError(
            "No se encontraron columnas de fecha en el CSV.\n"
            "Formatos aceptados: DD-MM-YYYY, YYYY-MM-DD, YYYY-MM-DD HH:MM:SS"
        )

    def get_week_start(date_str: str) -> str:
        """Retorna el domingo de la semana a la que pertenece la fecha (DD-MM-YYYY)."""
        d = datetime.strptime(date_str, "%d-%m-%Y")
        days_since_sunday = (d.weekday() + 1) % 7
        sunday = d - timedelta(days=days_since_sunday)
        return sunday.strftime("%Y-%m-%d")

    weeks = defaultdict(list)
    for row in rows:
        task_name = row.get("Task Name", "").strip()
        if not task_name:
            continue

        grant_id = row.get("Grant ID", "").strip()

        # Construir dict de horas usando fecha normalizada DD-MM-YYYY como clave
        hours_by_date = {}
        has_hours = False
        for col, norm_date in date_columns.items():
            raw = row.get(col, "0").strip().replace(",", ".")
            try:
                val = float(raw)
            except ValueError:
                val = 0.0
            hours_by_date[norm_date] = val
            if val > 0:
                has_hours = True

        # Omitir filas con todo en 0
        if not has_hours:
            continue

        # Agrupar por semana
        weeks_for_project = defaultdict(dict)
        for date_str, hrs in hours_by_date.items():
            week_key = get_week_start(date_str)
            weeks_for_project[week_key][date_str] = hrs

        for week_key, hours in weeks_for_project.items():
            weeks[week_key].append({
                "task_name": task_name,
                "grant_id": grant_id,  # ← incluir Grant ID en el resultado
                "hours": hours,
            })

    if not weeks:
        raise ValueError(
            "No se encontraron datos con horas > 0 en el CSV.\n"
            "Verifica que el archivo tenga datos válidos."
        )

    # Ordenar semanas cronológicamente
    return dict(sorted(weeks.items()))

def get_week_dates(week_start: str) -> list:
    """
    Retorna la lista de 7 fechas (dom a sáb) de una semana.
    week_start: string 'YYYY-MM-DD' del domingo.
    """
    start = datetime.strptime(week_start, "%Y-%m-%d")
    return [(start + timedelta(days=i)).strftime("%d-%m-%Y") for i in range(7)]
def format_hours(value: float) -> str:
    """
    Convierte un float a string con coma decimal para Workday.
    Ejemplos: 2.5 -> "2,5" | 0.25 -> "0,25" | 8.0 -> "8"
    """
    if value == int(value):
        return str(int(value))
    return str(value).replace(".", ",")