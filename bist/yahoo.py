"""Yahoo Finance herkese açık grafik ve temel veri uç noktaları.

Önemli: Yahoo'nun BIST verisi GERÇEK ZAMANLI DEĞİLDİR; genellikle ~15 dakika
gecikmelidir. Gecikme her çalıştırmada son mum zamanından ölçülür ve raporda
gösterilir. Hiçbir fiyat uydurulmaz: veri yoksa Series.error dolu döner.
"""
from __future__ import annotations

import datetime as dt
import time
import urllib.parse
from dataclasses import dataclass, field

from .tz import IST, to_ist

BASES = ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"]
SOURCE_NAME = "Yahoo Finance (ücretsiz, ~15 dk gecikmeli)"


def symbol_for(ticker: str) -> str:
    t = ticker.strip().upper()
    if t.startswith("^") or "=" in t or "." in t or "-" in t:
        return t
    return t + ".IS"


@dataclass
class Series:
    symbol: str
    interval: str
    t: list = field(default_factory=list)
    o: list = field(default_factory=list)
    h: list = field(default_factory=list)
    l: list = field(default_factory=list)
    c: list = field(default_factory=list)
    v: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    dividends: list = field(default_factory=list)  # [(ts, amount)]
    fetched_at: float = 0.0
    error: str | None = None
    missing_volume: int = 0

    def __len__(self) -> int:
        return len(self.c)

    @property
    def ok(self) -> bool:
        return self.error is None and len(self.c) > 0

    @property
    def last_time(self) -> dt.datetime | None:
        return to_ist(self.t[-1]) if self.t else None

    @property
    def name(self) -> str:
        return self.meta.get("shortName") or self.meta.get("longName") or self.symbol

    def dates(self) -> list[dt.date]:
        return [to_ist(x).date() for x in self.t]

    def slice_from(self, idx: int) -> "Series":
        return Series(self.symbol, self.interval, self.t[idx:], self.o[idx:], self.h[idx:], self.l[idx:],
                      self.c[idx:], self.v[idx:], self.meta, self.dividends, self.fetched_at, self.error)

    def only_date(self, day: dt.date) -> "Series":
        ds = self.dates()
        idx = [i for i, d in enumerate(ds) if d == day]
        if not idx:
            return Series(self.symbol, self.interval, meta=self.meta, fetched_at=self.fetched_at,
                          error=self.error)
        a, b = idx[0], idx[-1] + 1
        return Series(self.symbol, self.interval, self.t[a:b], self.o[a:b], self.h[a:b], self.l[a:b],
                      self.c[a:b], self.v[a:b], self.meta, self.dividends, self.fetched_at, self.error)

    def before_date(self, day: dt.date) -> "Series":
        ds = self.dates()
        idx = [i for i, d in enumerate(ds) if d < day]
        b = (idx[-1] + 1) if idx else 0
        return Series(self.symbol, self.interval, self.t[:b], self.o[:b], self.h[:b], self.l[:b],
                      self.c[:b], self.v[:b], self.meta, self.dividends, self.fetched_at, self.error)


def empty(symbol: str, interval: str, error: str) -> Series:
    return Series(symbol, interval, fetched_at=time.time(), error=error)


def parse_chart(data: dict, symbol: str, interval: str) -> Series:
    chart = (data or {}).get("chart") or {}
    res = chart.get("result")
    if not res:
        err = (chart.get("error") or {}).get("description") or "sonuç yok"
        return empty(symbol, interval, err)
    r = res[0]
    meta = r.get("meta") or {}
    ts = r.get("timestamp") or []
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0] or {}
    oo, hh, ll, cc, vv = (q.get(k) or [] for k in ("open", "high", "low", "close", "volume"))
    s = Series(symbol, interval, meta=meta, fetched_at=time.time())
    last_day = None
    for i, t in enumerate(ts):
        try:
            o, h, l, c = oo[i], hh[i], ll[i], cc[i]
        except IndexError:
            continue
        if c is None or o is None or h is None or l is None:
            continue
        v = vv[i] if i < len(vv) else None
        if v is None:
            v = 0
            s.missing_volume += 1
        # Günlük veride aynı güne ait mükerrer satırları birleştir (sonuncusu geçerli).
        if interval in ("1d", "1wk", "1mo"):
            d = to_ist(t).date()
            if d == last_day and s.t:
                s.t[-1], s.o[-1], s.h[-1], s.l[-1], s.c[-1], s.v[-1] = t, o, h, l, c, v
                continue
            last_day = d
        s.t.append(int(t))
        s.o.append(float(o))
        s.h.append(float(h))
        s.l.append(float(l))
        s.c.append(float(c))
        s.v.append(float(v))
    divs = ((r.get("events") or {}).get("dividends") or {})
    s.dividends = sorted((int(d.get("date", k)), float(d.get("amount", 0))) for k, d in divs.items())
    if not s.c:
        s.error = "boş veri"
    return s


def chart(client, ticker: str, rng: str = "1y", interval: str = "1d", events: bool = False) -> Series:
    sym = symbol_for(ticker)
    q = {"range": rng, "interval": interval, "includePrePost": "false"}
    if events:
        q["events"] = "div,split"
    last_err = "bilinmeyen hata"
    for base in BASES:
        url = f"{base}/v8/finance/chart/{urllib.parse.quote(sym)}?{urllib.parse.urlencode(q)}"
        try:
            s = parse_chart(client.json(url), sym, interval)
            return s
        except Exception as e:  # ağ hatası: diğer sunucuyu dene
            last_err = str(e)
    return empty(sym, interval, last_err)


def daily_change(s: Series) -> dict:
    """Son fiyat ve önceki kapanışa göre değişim (anlık/gecikmeli fiyat dahil)."""
    if not s.ok:
        return {"price": None, "prev": None, "chg": None, "time": None}
    price = s.meta.get("regularMarketPrice") or s.c[-1]
    mtime = s.meta.get("regularMarketTime") or s.t[-1]
    last_bar_day = to_ist(s.t[-1]).date()
    mday = to_ist(mtime).date()
    if mday == last_bar_day and len(s.c) >= 2:
        prev = s.c[-2]
    elif mday > last_bar_day:
        prev = s.c[-1]
    else:
        prev = s.c[-2] if len(s.c) >= 2 else None
    chg = (price / prev - 1) * 100 if prev else None
    return {"price": float(price), "prev": prev, "chg": chg, "time": to_ist(mtime)}


FUND_TYPES = [
    "annualTotalRevenue", "annualEBITDA", "annualNetIncome", "annualFreeCashFlow",
    "annualOperatingCashFlow", "annualTotalDebt", "annualCashAndCashEquivalents",
    "annualStockholdersEquity", "annualEBIT", "annualInvestedCapital", "annualGrossProfit",
    "trailingPeRatio", "trailingPbRatio", "trailingEnterprisesValueEBITDARatio", "trailingMarketCap",
]


def parse_timeseries(data: dict) -> dict:
    out = {"annual": {}, "trailing": {}}
    res = ((data or {}).get("timeseries") or {}).get("result") or []
    for item in res:
        typ = ((item.get("meta") or {}).get("type") or [None])[0]
        if not typ:
            continue
        rows = []
        for row in item.get(typ) or []:
            if not row:
                continue
            val = (row.get("reportedValue") or {}).get("raw")
            if val is None:
                continue
            rows.append({"date": row.get("asOfDate"), "value": float(val), "ccy": row.get("currencyCode")})
        rows.sort(key=lambda r: r["date"] or "")
        if typ.startswith("annual"):
            out["annual"][typ[len("annual"):]] = rows
        elif typ.startswith("trailing"):
            out["trailing"][typ[len("trailing"):]] = rows[-1] if rows else None
    return out


def fundamentals(client, ticker: str, now: float | None = None) -> dict:
    sym = symbol_for(ticker)
    now = int(now or time.time())
    p1 = now - 6 * 366 * 86400
    q = {"type": ",".join(FUND_TYPES), "period1": p1, "period2": now}
    last_err = None
    for base in BASES:
        url = f"{base}/ws/fundamentals-timeseries/v1/finance/timeseries/{urllib.parse.quote(sym)}?{urllib.parse.urlencode(q)}"
        try:
            parsed = parse_timeseries(client.json(url))
            parsed["fetched_at"] = now
            return parsed
        except Exception as e:
            last_err = str(e)
    return {"annual": {}, "trailing": {}, "fetched_at": now, "error": last_err}
