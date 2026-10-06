# ============================================================
# CLI — ejecuta pasos del pipeline respondiendo callbacks por consola.
# Ejemplos:
#   python cli.py report  --db C:\ruta\DataBase.xlsx --month 2026-10
#   python cli.py workday --db ... --month 2026-10
#   python cli.py n4w     --db ... --month 2026-10 --email yo@tnc.org
#   python cli.py all     --db ... --month 2026-10 --email yo@tnc.org [--prorate]
# ============================================================
import argparse
import sys
from datetime import datetime

from core.timesheet import align_to_full_weeks, month_range
from pipeline import Callbacks, Cancelled, Decision, Pipeline


def console_decide(d: Decision):
    print(f"\n? {d.question}")
    for i, opt in enumerate(d.options, 1):
        print(f"  {i}. {opt}")
    hint = "números separados por coma, Enter = todos" if d.multi else "número"
    raw = input(f"  ({hint}, 'c' = cancelar): ").strip()
    if raw.lower() == 'c':
        return None
    if d.multi:
        if not raw:
            return list(d.options)
        return [d.options[int(x) - 1] for x in raw.split(',') if x.strip()]
    return d.options[int(raw) - 1]


def console_approve(title: str, detail: str) -> bool:
    print(f"\n=== {title} ===\n{detail}")
    return input("¿Continuar? [s/N]: ").strip().lower() in ('s', 'si', 'sí', 'y', 'yes')


def parse_period(args) -> tuple:
    if args.month:
        y, m = map(int, args.month.split('-'))
        return month_range(y, m)
    if not (args.start and args.end):
        sys.exit("Indica --month YYYY-MM o --start/--end YYYY-MM-DD")
    start = datetime.strptime(args.start, '%Y-%m-%d')
    end = datetime.strptime(args.end, '%Y-%m-%d')
    return align_to_full_weeks(start, end)


def main():
    p = argparse.ArgumentParser(description="TimeSheet Agent — pipeline guiado")
    p.add_argument('step', choices=['update-db', 'categories', 'report', 'prorate', 'workday', 'n4w', 'all'])
    p.add_argument('--db', required=True, help="Ruta a la BD de proyectos (Excel)")
    p.add_argument('--month', help="YYYY-MM (se ajusta a semanas lun–dom completas)")
    p.add_argument('--start')
    p.add_argument('--end')
    p.add_argument('--email')
    p.add_argument('--prorate', action='store_true', help="En 'all': prorratear antes de Workday/N4W")
    p.add_argument('--csv', help="CSV alternativo para workday/n4w")
    p.add_argument('--no-week-confirm', action='store_true', help="Workday: no confirmar cada semana")
    args = p.parse_args()

    start, end = parse_period(args)
    print(f"Periodo: {start:%Y-%m-%d} → {end:%Y-%m-%d}")
    cb = Callbacks(log=print, decide=console_decide, approve=console_approve)
    pipe = Pipeline(args.db, start, end, email=args.email, callbacks=cb)
    confirm_weeks = not args.no_week_confirm

    try:
        if args.step == 'update-db':
            pipe.update_database()
        elif args.step == 'categories':
            pipe.sync_categories()
        elif args.step == 'report':
            pipe.build_timesheet()
        elif args.step == 'prorate':
            pipe.prorate()
        elif args.step == 'workday':
            pipe.fill_workday(args.csv, confirm_each_week=confirm_weeks)
        elif args.step == 'n4w':
            pipe.submit_n4w(args.csv)
        elif args.step == 'all':
            pipe.update_database()
            findings = pipe.build_timesheet()
            csv = pipe.prorate() if args.prorate else None
            if not console_approve("Resumen del periodo", findings['summary'].to_string()):
                raise Cancelled("Resumen no aprobado")
            pipe.fill_workday(csv, confirm_each_week=confirm_weeks)
            pipe.submit_n4w()   # N4W siempre usa 02-Timesheet.csv (sin prorrateo), como el original
    except Cancelled as e:
        print(f"\n✗ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
