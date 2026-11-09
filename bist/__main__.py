"""Komut satırı.

  python -m bist plan  [--event schedule] [--slot auto]   -> beklenecek süre (GitHub Actions için)
  python -m bist run   [--slot auto|premarket|opening|midday|close] [--force] [--trigger manual]
  python -m bist site  --out _site                         -> mobil web sitesini üretir
  python -m bist note  --message "..."                     -> çalışma günlüğüne not
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sys
import traceback
from pathlib import Path

from . import config as C
from .net import HttpClient
from .state import State, due_slots, wait_seconds
from .tz import SLOT_ORDER, SLOTS, now_ist

ROOT = Path(os.environ.get("BIST_ROOT", Path(__file__).resolve().parent.parent))


def gh_output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    for k, v in kv.items():
        print(f"{k}={v}")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def cmd_plan(a) -> int:
    cfg = C.load(ROOT)
    st = State(cfg.data_dir)
    now = now_ist()
    trading = cfg.calendar.is_trading_day(now.date())
    w = wait_seconds(now, st, trading) if (a.event == "schedule" and a.slot == "auto") else 0
    gh_output(wait=w)
    return 0


def prune_reports(cfg, keep_days: int, today: dt.date):
    base = cfg.data_dir / "reports"
    if not base.exists():
        return
    for d in base.iterdir():
        try:
            day = dt.date.fromisoformat(d.name)
        except ValueError:
            continue
        if (today - day).days > keep_days:
            shutil.rmtree(d, ignore_errors=True)


def cmd_run(a) -> int:
    from .config import Context
    from .reports import generate

    cfg = C.load(ROOT)
    st = State(cfg.data_dir)
    now = now_ist()
    client = HttpClient(timeout=float(cfg.get("network", "timeout_sec", default=20)),
                        min_interval=float(cfg.get("network", "min_interval_sec", default=0.15)))
    today = now.date()
    day_st, day_note = cfg.calendar.status(today)
    trading = day_st != "closed"
    changed = False
    failed = []
    if a.slot == "auto":
        if not trading:
            if not st.day(today):
                st.set_day(today, "closed", day_note)
                st.log(now, "holiday", None, "info", f"Bugün işlem yok: {day_note}")
                changed = True
            slots = []
        else:
            slots = due_slots(now, st, trading)
            if not cfg.calendar.calendar_known(today):
                st.log(now, "calendar", None, "warning", f"{today.year} yılı tatil takvimi config/calendar.json içinde yok")
    else:
        slots = [a.slot]
        if st.done(today, a.slot) and not a.force:
            print(f"{a.slot} raporu bugün zaten üretilmiş (yeniden üretmek için --force).")
            slots = []
    for slot in slots:
        ctx = Context(cfg, client, now_ist(), trigger=a.trigger)
        try:
            rep = generate(ctx, slot, refresh_fund=a.refresh_fundamentals)
            st.mark(today, slot, rep["status"], generated_at=rep["generated_at"], delay_minutes=rep["delay_minutes"],
                    trigger=a.trigger, quality=rep["data_quality"]["overall"], headline=rep["headline"])
            st.log(ctx.now, "report", slot, rep["status"],
                   f"{SLOTS[slot]['title']} üretildi ({rep['delay_minutes']:+d} dk, kalite: {rep['data_quality']['label']})")
            changed = True
            print(f"OK {slot}: {rep['headline']}")
        except Exception as e:
            tb = traceback.format_exc(limit=4)
            print(tb, file=sys.stderr)
            st.mark(today, slot, "failed", error=str(e)[:300], trigger=a.trigger, at=now_ist().isoformat(timespec="seconds"))
            st.log(now_ist(), "report", slot, "error", f"Rapor üretilemedi: {str(e)[:200]}")
            failed.append(slot)
            changed = True
    if st.mark_missed(now_ist(), trading):
        changed = True
    st.data["last_run"] = {"at": now_ist().isoformat(timespec="seconds"), "trigger": a.trigger, "slots": slots,
                           "failed": failed, "requests": client.stats["requests"], "fetch_failures": client.stats["failures"]}
    st.save()
    prune_reports(cfg, int(cfg.get("report_keep_days", default=400)), today)
    gh_output(changed=str(changed).lower(), failed=",".join(failed))
    return 1 if failed else 0


def cmd_site(a) -> int:
    from .site import build
    cfg = C.load(ROOT)
    build(cfg, Path(a.out))
    print(f"Site üretildi: {a.out}")
    return 0


def cmd_note(a) -> int:
    cfg = C.load(ROOT)
    st = State(cfg.data_dir)
    st.log(now_ist(), "workflow", None, a.status, a.message)
    st.save()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="bist")
    sub = p.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("plan")
    pp.add_argument("--event", default="schedule")
    pp.add_argument("--slot", default="auto")
    pr = sub.add_parser("run")
    pr.add_argument("--slot", default="auto", choices=["auto"] + SLOT_ORDER)
    pr.add_argument("--force", action="store_true")
    pr.add_argument("--trigger", default="schedule")
    pr.add_argument("--refresh-fundamentals", default=None, help="'all' = tüm temel verileri yenile")
    ps = sub.add_parser("site")
    ps.add_argument("--out", default="_site")
    pn = sub.add_parser("note")
    pn.add_argument("--message", required=True)
    pn.add_argument("--status", default="error")
    a = p.parse_args(argv)
    return {"plan": cmd_plan, "run": cmd_run, "site": cmd_site, "note": cmd_note}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
