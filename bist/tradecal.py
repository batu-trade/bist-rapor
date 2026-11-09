"""Borsa İstanbul işlem günü takvimi."""
from __future__ import annotations

import datetime as dt

from .tz import IST, at, parse_hm


class TradingCalendar:
    def __init__(self, cfg: dict):
        self.holidays: dict[str, str] = dict(cfg.get("holidays", {}))
        self.half_days: dict[str, str] = dict(cfg.get("half_days", {}))
        sess = cfg.get("session", {})
        self.open_hm = parse_hm(sess.get("open", "10:00"))
        self.close_hm = parse_hm(sess.get("close", "18:00"))
        self.half_close_hm = parse_hm(sess.get("half_day_close", "12:30"))
        years = {k[:4] for k in self.holidays}
        self.known_years = years

    def status(self, day: dt.date) -> tuple[str, str]:
        """('closed'|'half'|'open', açıklama)."""
        key = day.isoformat()
        if day.weekday() >= 5:
            return "closed", "Hafta sonu"
        if key in self.holidays:
            return "closed", self.holidays[key]
        if key in self.half_days:
            return "half", self.half_days[key]
        return "open", ""

    def is_trading_day(self, day: dt.date) -> bool:
        return self.status(day)[0] != "closed"

    def calendar_known(self, day: dt.date) -> bool:
        return str(day.year) in self.known_years

    def previous_trading_day(self, day: dt.date) -> dt.date:
        d = day - dt.timedelta(days=1)
        while not self.is_trading_day(d):
            d -= dt.timedelta(days=1)
        return d

    def next_trading_day(self, day: dt.date) -> dt.date:
        d = day + dt.timedelta(days=1)
        while not self.is_trading_day(d):
            d += dt.timedelta(days=1)
        return d

    def session(self, day: dt.date) -> tuple[dt.datetime, dt.datetime]:
        st, _ = self.status(day)
        close = self.half_close_hm if st == "half" else self.close_hm
        return at(day, self.open_hm), at(day, close)

    def phase(self, now: dt.datetime) -> str:
        """'pre' (açılış öncesi), 'open' (seans), 'post' (kapanış sonrası), 'closed' (tatil)."""
        now = now.astimezone(IST)
        if not self.is_trading_day(now.date()):
            return "closed"
        o, c = self.session(now.date())
        if now < o:
            return "pre"
        if now <= c + dt.timedelta(minutes=10):
            return "open"
        return "post"
