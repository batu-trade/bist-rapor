"""Çalıştırma durumu: mükerrer rapor önleme, çalışma günlüğü, kaçırılan rapor tespiti."""
from __future__ import annotations

import datetime as dt

from .tz import SLOT_ORDER, SLOTS, slot_deadline, slot_time
from .util import load_json, save_json

MAX_LOG = 400


class State:
    def __init__(self, data_dir):
        self.path = data_dir / "state" / "runs.json"
        self.data = load_json(self.path, None) or {"reports": {}, "log": [], "days": {}}
        self.data.setdefault("days", {})

    def save(self):
        self.data["log"] = self.data["log"][-MAX_LOG:]
        # 120 günden eski rapor kayıtlarını sil
        keys = sorted(self.data["reports"])
        for k in keys[:-120]:
            del self.data["reports"][k]
        for k in sorted(self.data["days"])[:-120]:
            del self.data["days"][k]
        save_json(self.path, self.data)

    def entry(self, day: dt.date, slot: str) -> dict | None:
        return self.data["reports"].get(day.isoformat(), {}).get(slot)

    def done(self, day: dt.date, slot: str) -> bool:
        e = self.entry(day, slot)
        return bool(e and e.get("status") in ("ok", "partial"))

    def mark(self, day: dt.date, slot: str, status: str, **info):
        self.data["reports"].setdefault(day.isoformat(), {})[slot] = {"status": status, **info}

    def set_day(self, day: dt.date, status: str, note: str):
        self.data["days"][day.isoformat()] = {"status": status, "note": note}

    def day(self, day: dt.date) -> dict | None:
        return self.data["days"].get(day.isoformat())

    def log(self, now: dt.datetime, event: str, slot: str | None = None, status: str = "info", message: str = ""):
        self.data["log"].append({"ts": now.isoformat(timespec="seconds"), "event": event, "slot": slot,
                                 "status": status, "message": message})

    def mark_missed(self, now: dt.datetime, is_trading_day: bool) -> list[str]:
        if not is_trading_day:
            return []
        day = now.date()
        missed = []
        for s in SLOT_ORDER:
            if now > slot_deadline(day, s) and not self.entry(day, s):
                self.mark(day, s, "missed", note=f"{SLOTS[s]['short']} raporu zamanında üretilemedi "
                                                f"(bulut zamanlayıcısı gecikmiş/atlamış olabilir). Elle üretilebilir.")
                self.log(now, "missed", s, "warning", "Rapor süresi içinde üretilemedi")
                missed.append(s)
        return missed


def due_slots(now: dt.datetime, state: State, is_trading_day: bool) -> list[str]:
    """Şu an üretilmesi gereken (zamanı gelmiş, süresi geçmemiş, henüz üretilmemiş) raporlar."""
    if not is_trading_day:
        return []
    day = now.date()
    out = []
    for s in SLOT_ORDER:
        if slot_time(day, s) <= now <= slot_deadline(day, s) and not state.done(day, s):
            out.append(s)
    return out


def wait_seconds(now: dt.datetime, state: State, is_trading_day: bool, max_wait_min: int = 40) -> int:
    """Zamanlanmış tetikleme erken geldiyse, sıradaki rapor saatine kadar beklenecek süre."""
    if not is_trading_day or due_slots(now, state, is_trading_day):
        return 0
    day = now.date()
    for s in SLOT_ORDER:
        st = slot_time(day, s)
        if st > now and not state.done(day, s):
            secs = (st - now).total_seconds()
            if secs <= max_wait_min * 60:
                return int(secs) + 5
            return 0
    return 0
