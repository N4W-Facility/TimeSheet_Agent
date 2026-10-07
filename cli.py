# ============================================================
# CLI — ejecuta flujos respondiendo callbacks por consola.
#   python cli.py report  --month 2026-10
#   python cli.py workday --month 2026-10   (prorratea si hace falta)
#   python cli.py n4w     --start 2026-10-05 --end 2026-10-25 --email me@tnc.org
#   python cli.py n4w     --month 2026-10 --email me@tnc.org   (pregunta semanas)
#   python cli.py categories   (crea en Outlook las categorías de "mis proyectos")
# Archivos en --workdir (por defecto config.WORK_DIR).
# ============================================================
import argparse
import sys

import config
import workflows
from core import timesheet
from core.history import History
from pipeline import Callbacks, Cancelled, Decision, Pipeline


def console_decide(d: Decision):
    print(f"\n? {d.question}")
    for i, opt in enumerate(d.options, 1):
        print(f"  {i}. {opt}")
    hint = "comma-separated numbers, Enter = all" if d.multi else "number"
    raw = input(f"  ({hint}, 'c' = cancel): ").strip()
    if raw.lower() == 'c':
        return None
    if d.multi:
        if not raw:
            return list(d.options)
        return [d.options[int(x) - 1] for x in raw.split(',') if x.strip()]
    return d.options[int(raw) - 1]


def console_approve(title: str, detail: str) -> bool:
    print(f"\n=== {title} ===\n{detail}")
    return input("Continue? [y/N]: ").strip().lower() in ('y', 'yes', 's', 'si', 'sí')


def main():
    p = argparse.ArgumentParser(description="TimeSheet Agent — guided pipeline")
    p.add_argument('step', choices=['refresh', 'categories', 'report', 'workday', 'n4w'])
    p.add_argument('--workdir', help="Folder for generated files (default: Documents/TimeSheetAgent)")
    p.add_argument('--month', help="YYYY-MM")
    p.add_argument('--start', help="YYYY-MM-DD (report/n4w)")
    p.add_argument('--end', help="YYYY-MM-DD (report/n4w)")
    p.add_argument('--email')
    p.add_argument('--no-week-confirm', action='store_true', help="workday: don't confirm each week")
    p.add_argument('--skip-refresh', action='store_true', help="don't download N4W_Task_Details")
    args = p.parse_args()

    cb = Callbacks(log=print, decide=console_decide, approve=console_approve)
    pipe = Pipeline(args.workdir, email=args.email, callbacks=cb)
    refresh = not args.skip_refresh

    try:
        if args.step == 'refresh':
            pipe.refresh_task_details()
        elif args.step == 'categories':
            for name in pipe.create_categories(History(config.HISTORY_DB).my_projects()):
                print(f"  + {name}")
        elif args.step == 'report':
            if args.month:
                start, end = timesheet.month_bounds(*workflows.parse_month(args.month))
            else:
                start, end = workflows.parse_weeks(args.start, args.end)
            workflows.run_report(pipe, start, end, refresh)
        elif args.step == 'workday':
            y, m = workflows.parse_month(args.month)
            workflows.run_workday_month(pipe, y, m, not args.no_week_confirm, refresh)
        elif args.step == 'n4w':
            if args.start and args.end:
                start, end = workflows.parse_weeks(args.start, args.end)
            else:
                start, end = workflows.choose_n4w_weeks(pipe, *workflows.parse_month(args.month))
            workflows.run_n4w(pipe, start, end, refresh)
    except Cancelled as e:
        print(f"\n✗ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
