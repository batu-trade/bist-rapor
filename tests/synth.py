"""Testler için sentetik ama gerçekçi Yahoo grafik yanıtları üretir."""
from __future__ import annotations

import datetime as dt
import random
import re
import urllib.parse
import zlib

from bist.tz import IST

UTC = dt.timezone.utc


def trading_days(end: dt.date, n: int, cal) -> list[dt.date]:
    out, d = [], end
    while len(out) < n:
        if cal.is_trading_day(d):
            out.append(d)
        d -= dt.timedelta(days=1)
    return list(reversed(out))


def _rng(sym: str) -> random.Random:
    return random.Random(zlib.crc32(sym.encode()))


def daily_json(sym: str, now: dt.datetime, cal, n: int = 500, trend: float = 0.0006) -> dict:
    rnd = _rng(sym)
    end = now.date()
    o_s, _ = cal.session(end) if cal.is_trading_day(end) else (None, None)
    include_today = cal.is_trading_day(end) and o_s is not None and now >= o_s + dt.timedelta(minutes=5)
    days = trading_days(end if include_today else cal.previous_trading_day(end), n, cal)
    p = 50 + rnd.random() * 200
    ts, o, h, l, c, v = [], [], [], [], [], []
    for d in days:
        op = p * (1 + rnd.gauss(0, 0.004))
        cl = op * (1 + rnd.gauss(trend, 0.016))
        hi = max(op, cl) * (1 + abs(rnd.gauss(0, 0.006)))
        lo = min(op, cl) * (1 - abs(rnd.gauss(0, 0.006)))
        ts.append(int(dt.datetime(d.year, d.month, d.day, 9, 55, tzinfo=IST).timestamp()))
        o.append(round(op, 2)); h.append(round(hi, 2)); l.append(round(lo, 2)); c.append(round(cl, 2))
        v.append(int(rnd.uniform(2e6, 8e6)))
        p = cl
    meta = {"symbol": sym, "shortName": sym.replace(".IS", "") + " A.S.", "regularMarketPrice": c[-1],
            "regularMarketTime": int(min(now.timestamp(), ts[-1] + 8 * 3600)), "currency": "TRY"}
    return {"chart": {"result": [{"meta": meta, "timestamp": ts, "events": {"dividends": {str(ts[-100]): {"amount": 1.5, "date": ts[-100]}}},
                                  "indicators": {"quote": [{"open": o, "high": h, "low": l, "close": c, "volume": v}]}}], "error": None}}


def intraday_json(sym: str, now: dt.datetime, cal, delay_min: int = 15, breakout: bool = False) -> dict:
    rnd = _rng(sym + "i")
    days = trading_days(now.date() if cal.is_trading_day(now.date()) else cal.previous_trading_day(now.date()), 5, cal)
    p = 100 + rnd.random() * 50
    ts, o, h, l, c, v = [], [], [], [], [], []
    cutoff = now - dt.timedelta(minutes=delay_min)
    for d in days:
        o_s, c_s = cal.session(d)
        t = o_s - dt.timedelta(minutes=5)
        k = 0
        while t <= c_s - dt.timedelta(minutes=5):
            if t + dt.timedelta(minutes=5) > cutoff:
                break
            drift = 0.0009 if (breakout and d == now.date() and k > 6) else 0.0
            op = p
            cl = op * (1 + rnd.gauss(drift, 0.0025))
            hi = max(op, cl) * (1 + abs(rnd.gauss(0, 0.001)))
            lo = min(op, cl) * (1 - abs(rnd.gauss(0, 0.001)))
            vol = rnd.uniform(5e4, 2e5) * (3 if (breakout and d == now.date()) else 1)
            ts.append(int(t.timestamp())); o.append(round(op, 3)); h.append(round(hi, 3)); l.append(round(lo, 3))
            c.append(round(cl, 3)); v.append(int(vol))
            p = cl
            t += dt.timedelta(minutes=5)
            k += 1
    meta = {"symbol": sym, "shortName": sym, "regularMarketPrice": c[-1] if c else None,
            "regularMarketTime": ts[-1] if ts else None}
    return {"chart": {"result": [{"meta": meta, "timestamp": ts,
                                  "indicators": {"quote": [{"open": o, "high": h, "low": l, "close": c, "volume": v}]}}], "error": None}}


def router(now_fn, cal, breakout_syms=(), fail_all=False):
    def chart(url):
        if fail_all:
            raise ConnectionError("ağ yok (test)")
        m = re.search(r"/v8/finance/chart/([^?]+)\?(.*)", url)
        sym = urllib.parse.unquote(m.group(1))
        q = urllib.parse.parse_qs(m.group(2))
        iv = q["interval"][0]
        now = now_fn()
        if iv in ("5m", "1m"):
            return intraday_json(sym, now, cal, breakout=sym.replace(".IS", "") in breakout_syms)
        if iv == "1mo":
            return daily_json(sym, now, cal, n=60)
        n = {"1mo": 22, "3mo": 65, "1y": 250, "2y": 500, "5y": 1200}.get(q["range"][0], 250)
        return daily_json(sym, now, cal, n=n)
    return chart
