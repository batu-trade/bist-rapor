"""Yapılandırma ve çalışma bağlamı."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

from .tradecal import TradingCalendar
from .tz import IST, now_ist
from .util import load_json


def read_watchlist(path: Path) -> list[str]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        t = line.split("#", 1)[0].strip().upper().replace(".IS", "")
        if t and t.isalnum() and t not in out:
            out.append(t)
    return out


@dataclass
class Config:
    root: Path
    settings: dict
    universe: dict
    calendar: TradingCalendar
    macro: dict
    watchlist: list

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    def stocks(self) -> dict:
        st = {k: dict(v) for k, v in self.universe.get("stocks", {}).items() if not v.get("disabled")}
        for t in self.watchlist:
            if t not in st:
                st[t] = {"sector": "Diğer", "si": None, "bist30": False}
        for t in st:
            st[t]["watch"] = t in self.watchlist
        return st

    def get(self, *keys, default=None):
        cur = self.settings
        for k in keys:
            if not isinstance(cur, dict) or k not in cur:
                return default
            cur = cur[k]
        return cur


def load(root: str | Path) -> Config:
    root = Path(root)
    c = root / "config"
    return Config(
        root=root,
        settings=load_json(c / "settings.json", {}) or {},
        universe=load_json(c / "universe.json", {}) or {},
        calendar=TradingCalendar(load_json(c / "calendar.json", {}) or {}),
        macro=load_json(c / "macro.json", {}) or {},
        watchlist=read_watchlist(c / "watchlist.txt"),
    )


@dataclass
class Context:
    cfg: Config
    client: object
    now: dt.datetime = field(default_factory=now_ist)
    trigger: str = "schedule"

    @property
    def today(self) -> dt.date:
        return self.now.astimezone(IST).date()

    @property
    def cal(self) -> TradingCalendar:
        return self.cfg.calendar

    @property
    def phase(self) -> str:
        return self.cal.phase(self.now)

    @property
    def session(self):
        d = self.today if self.cal.is_trading_day(self.today) else self.cal.next_trading_day(self.today)
        return self.cal.session(d)

    @property
    def expected_daily_last(self) -> dt.date:
        """Günlük veride beklenen son gün."""
        if self.cal.is_trading_day(self.today) and self.phase in ("open", "post"):
            # Ücretsiz veri ~15 dk gecikmeli: açılıştan sonraki ilk 20 dakikada
            # bugünün mumu henüz görünmeyebilir; bu durumda dünkü veri bayat sayılmaz.
            if self.now >= self.cal.session(self.today)[0] + dt.timedelta(minutes=20):
                return self.today
        return self.cal.previous_trading_day(self.today)
        return self.cal.previous_trading_day(self.today)

    @property
    def workers(self) -> int:
        return int(self.cfg.get("network", "workers", default=4))
