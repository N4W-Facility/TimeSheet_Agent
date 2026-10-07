# ============================================================
# EVALUACIÓN DE MODELOS — precisión y velocidad de parse_intent
#   python eval_intents.py                       (modelo de config)
#   python eval_intents.py qwen3:1.7b qwen3:4b qwen3:8b
# Los modelos deben estar descargados (ollama pull <modelo>).
# Fechas relativas ("mes pasado") se calculan contra hoy.
# ============================================================
import sys
import time
from datetime import date

from agent import llm

TODAY = date.today()


def ym(offset: int = 0) -> str:
    """Mes relativo a hoy: 0 = este mes, -1 = mes pasado."""
    m = TODAY.year * 12 + TODAY.month - 1 + offset
    return f"{m // 12}-{m % 12 + 1:02d}"


def last(month: int) -> str:
    """Mes con nombre → su ocurrencia más reciente no futura."""
    year = TODAY.year if month <= TODAY.month else TODAY.year - 1
    return f"{year}-{month:02d}"


# (frase, acción esperada, campos esperados)
CASES = [
    # read_hours
    ("lee mis horas de septiembre", "read_hours", {"month": last(9)}),
    ("read my hours for last month", "read_hours", {"month": ym(-1)}),
    ("carga mis tiempos de este mes desde outlook", "read_hours", {"month": ym(0)}),
    ("leia minhas horas de agosto", "read_hours", {"month": last(8)}),
    ("lee mis horas del 1 al 15 de septiembre de 2026", "read_hours",
     {"start_date": "2026-09-01", "end_date": "2026-09-15"}),
    # prorate
    ("prorratea", "prorate", {}),
    ("prorate the hours", "prorate", {}),
    ("haz el prorrateo de las horas", "prorate", {}),
    # fill_workday
    ("llena workday", "fill_workday", {}),
    ("fill Workday for September", "fill_workday", {"month": last(9)}),
    ("preencher o workday", "fill_workday", {}),
    # submit_n4w
    ("envía N4W de septiembre", "submit_n4w", {"month": last(9)}),
    ("submit my hours to N4W facility for last month", "submit_n4w", {"month": ym(-1)}),
    # add_project
    ("estoy trabajando en un proyecto nuevo, el OF0123, crea la categoría", "add_project", {"project": "OF0123"}),
    ("add project N4W0456", "add_project", {"project": "N4W0456"}),
    ("ya no trabajo en SE3202", "remove_project", {"project": "SE3202"}),
    ("remove FS4302 from my projects", "remove_project", {"project": "FS4302"}),
    ("¿cuáles son mis proyectos?", "my_projects", {}),
    ("quais são os meus projetos?", "my_projects", {}),
    ("importa mis proyectos desde mi Excel", "import_projects", {}),
    ("import my projects from an Excel file", "import_projects", {}),
    # hours_summary
    ("dame un resumen de mis horas de agosto", "hours_summary", {"month": last(8)}),
    ("how many hours did I charge per project last month?", "hours_summary", {"month": ym(-1)}),
    # compare_months
    ("¿cargué más o menos horas que en agosto?", "compare_months", {"month2": last(8)}),
    ("compare September with August", "compare_months", {"month": last(9), "month2": last(8)}),
    ("compara este mes con el anterior", "compare_months", {"month": ym(0)}),
    # project_stats
    ("¿cuál es mi promedio en OF0104?", "project_stats", {"project": "OF0104"}),
    ("analiza los proyectos que tengo", "project_stats", {"project": None}),
    ("show my averages per project", "project_stats", {"project": None}),
    # set_target
    ("mi dedicación a OF0104 debería ser 30%", "set_target", {"project": "OF0104", "target_pct": 30}),
    ("I should spend 40 hours a month on P100", "set_target", {"project": "P100", "target_hours": 40}),
    # alerts
    ("¿tengo alguna alerta este mes?", "alerts", {"month": ym(0)}),
    ("check my hours for problems in August", "alerts", {"month": last(8)}),
    # load_history
    ("carga mi historial de los últimos 6 meses", "load_history", {"months_back": 6}),
    ("load my history", "load_history", {}),
    # other / help
    ("actualiza la base de datos de proyectos", "update_database", {}),
    ("sincroniza las categorías de outlook", "sync_categories", {}),
    ("¿qué puedes hacer?", "help", {}),
    ("what can you do?", "help", {}),
    ("¿cuál es la capital de Francia?", "other", {}),
    ("escribe un poema", "other", {}),
    # pedir todo junto → debe ser UN paso, nunca varios
    ("lee octubre, prorratea y llena workday", None, {}),
]


def check(intent: llm.Intent, action, fields) -> list:
    errors = []
    if action is not None and intent.action != action:
        errors.append(f"action={intent.action}")
    for k, v in fields.items():
        got = getattr(intent, k)
        if isinstance(v, (int, float)) and got is not None:
            ok = abs(float(got) - v) < 0.01
        else:
            ok = got == v
        if not ok:
            errors.append(f"{k}={got!r} (expected {v!r})")
    return errors


def run(model: str):
    print(f"\n=== {model} ===")
    ok, times = 0, []
    for text, action, fields in CASES:
        t0 = time.perf_counter()
        try:
            intent = llm.parse_intent(text, [], model=model)
            errors = check(intent, action, fields)
            got = intent.action
        except Exception as e:
            errors, got = [f"exception: {e}"], "-"
        times.append(time.perf_counter() - t0)
        ok += not errors
        mark = "✓" if not errors else "✗"
        print(f" {mark} {times[-1]:5.1f}s  {text[:55]:<55} → {got}"
              + (f"   [{'; '.join(errors)}]" if errors else ""))
    n = len(CASES)
    print(f"--- {model}: {ok}/{n} correct ({ok / n:.0%}) | "
          f"avg {sum(times) / n:.1f}s | first call {times[0]:.1f}s (model load)")
    return model, ok, n, sum(times[1:]) / max(1, n - 1)


def main():
    import config
    models = sys.argv[1:] or [config.OLLAMA_MODEL]
    results = [run(m) for m in models]
    print("\nSUMMARY")
    for model, ok, n, avg in results:
        print(f"  {model:<14} {ok}/{n} ({ok / n:.0%})  avg {avg:.1f}s")


if __name__ == "__main__":
    main()
