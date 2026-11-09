"""Hisse tarayıcı: likidite, hacim, göreceli hacim, momentum, oynaklık, olağandışı hareket."""
from __future__ import annotations

from . import fmt
import datetime as dt

from . import indicators as ind
from . import quality as Q
from . import yahoo
from .market import completed, trend_label
from .tz import to_ist
from .util import parallel_map, r


def relvol_time_of_day(intra, today: dt.date) -> float | None:
    """Bugün şu saate kadarki toplam hacim / önceki günlerin aynı saate kadarki ortalaması."""
    if intra is None or not intra.ok:
        return None
    by_day: dict[dt.date, list[tuple[int, float]]] = {}
    for t, v in zip(intra.t, intra.v):
        d = to_ist(t)
        by_day.setdefault(d.date(), []).append((d.hour * 60 + d.minute, v))
    if today not in by_day:
        return None
    tbars = by_day.pop(today)
    cutoff = tbars[-1][0]
    cum_today = sum(v for _, v in tbars)
    prior = [sum(v for m, v in bars if m <= cutoff) for bars in by_day.values()]
    prior = [p for p in prior if p > 0]
    if len(prior) < 2 or cum_today <= 0:
        return None
    return cum_today / (sum(prior) / len(prior))


def liquidity_class(avg_tl: float | None, cfg) -> str:
    if avg_tl is None:
        return "bilinmiyor"
    hi = cfg.get("liquidity_tl", "high", default=5e8)
    md = cfg.get("liquidity_tl", "medium", default=1e8)
    if avg_tl >= hi:
        return "yüksek"
    if avg_tl >= md:
        return "orta"
    return "düşük"


def snapshot(ticker: str, info: dict, daily, intra, ctx, index_closes: list | None) -> dict:
    o_s, c_s = ctx.session
    dq, dnote = Q.assess_daily(daily, ctx.now, ctx.expected_daily_last, o_s, c_s, min_len=60)
    snap = {
        "ticker": ticker, "sector": info.get("sector"), "si": info.get("si"), "bist30": info.get("bist30", False),
        "watch": info.get("watch", False), "q_daily": dq, "q_daily_note": dnote, "name": ticker,
    }
    if intra is not None:
        iq, inote, age = Q.assess_intraday(intra, ctx.now, o_s, c_s,
                                            min_bars=int(ctx.cfg.get("intraday", "min_bars", default=3)))
        snap.update({"q_intra": iq, "q_intra_note": inote, "delay_min": r(age, 0)})
    if not daily.ok:
        return snap
    snap["name"] = daily.name
    dc = yahoo.daily_change(daily)
    comp = completed(daily, ctx)
    cl, hh, ll, vv = comp.c, comp.h, comp.l, comp.v
    price = dc["price"]
    snap.update({"price": r(price), "prev": r(dc["prev"]), "chg": r(dc["chg"]),
                 "time": dc["time"].isoformat() if dc["time"] else None})
    if len(cl) < 30:
        snap["problems"] = ["yetersiz geçmiş"]
        return snap
    e20, e50, e200 = (ind.ema(cl, n) for n in (20, 50, 200))
    rsi_l = ind.rsi(cl)
    _, _, hist = ind.macd(cl)
    adx_l, pdi, mdi = ind.adx(hh, ll, cl)
    atr_l = ind.atr(hh, ll, cl)
    _, bbu, bbl = ind.bollinger(cl)
    atr = ind.last(atr_l)
    tlv = [c * v for c, v in zip(cl[-20:], vv[-20:])]
    avg_tl = sum(tlv) / len(tlv) if tlv else None
    avg_vol20 = sum(vv[-20:]) / min(20, len(vv)) if vv else None
    # Bugünkü hacim (seans içinde günlük veride kısmi mum vardır)
    today_vol = None
    if daily.dates()[-1] == ctx.today:
        today_vol = daily.v[-1]
    elif ctx.phase == "post" or ctx.phase == "pre":
        today_vol = None
    relvol = None
    rv_tod = relvol_time_of_day(intra, ctx.today) if intra is not None else None
    if rv_tod is not None:
        relvol = rv_tod
    elif today_vol is not None and avg_vol20 and ctx.phase == "post":
        relvol = today_vol / avg_vol20
    elif ctx.phase in ("pre", "closed") and avg_vol20 and vv:
        relvol = vv[-1] / (sum(vv[-21:-1]) / max(1, len(vv[-21:-1])))  # dünkü hacim / önceki 20 gün
    last_close = cl[-1]
    hist_hist = [x for x in hist if x is not None]

    def ret(n):
        return ind.pct_change(price, cl[-n - 1]) if len(cl) > n else None

    def rs(n):
        if not index_closes or len(index_closes) <= n or len(cl) <= n:
            return None
        a = ind.pct_change(cl[-1], cl[-n - 1])
        b = ind.pct_change(index_closes[-1], index_closes[-n - 1])
        return None if a is None or b is None else a - b

    trend = trend_label(last_close, ind.last(e20), ind.last(e50), ind.last(e200))
    sr = ind.support_resistance(hh, ll, cl, price)
    unusual = []
    if dc["chg"] is not None and abs(dc["chg"]) >= 4:
        unusual.append(f"Sert fiyat hareketi ({fmt.pct(dc['chg'], 1)})")
    if relvol is not None and relvol >= 2:
        unusual.append(f"Olağandışı hacim (normalin {fmt.num(relvol, 1)} katı)")
    if len(cl) >= 250 and price >= max(hh[-250:]) * 0.995:
        unusual.append("52 haftanın zirvesine yakın")
    if len(cl) >= 250 and price <= min(ll[-250:]) * 1.005:
        unusual.append("52 haftanın dibine yakın")
    snap.update({
        "tl_vol_today": r(today_vol * price, 0) if today_vol is not None else None,
        "avg_tl_vol20": r(avg_tl, 0), "liq": liquidity_class(avg_tl, ctx.cfg),
        "relvol": r(relvol), "relvol_kind": "gün içi (aynı saate göre)" if rv_tod is not None else "günlük",
        "ret5": r(ret(5)), "ret20": r(ret(20)), "ret60": r(ret(60)),
        "rs20": r(rs(20)), "rs60": r(rs(60)),
        "atr": r(atr, 3), "atr_pct": r(atr / price * 100 if atr and price else None),
        "rsi": r(ind.last(rsi_l), 1), "macd_hist": r(hist_hist[-1] if hist_hist else None, 4),
        "macd_hist_prev": r(hist_hist[-2] if len(hist_hist) > 1 else None, 4),
        "adx": r(ind.last(adx_l), 1), "pdi": r(ind.last(pdi), 1), "mdi": r(ind.last(mdi), 1),
        "ema20": r(ind.last(e20)), "ema50": r(ind.last(e50)), "ema200": r(ind.last(e200)),
        "bb_up": r(ind.last(bbu)), "bb_lo": r(ind.last(bbl)),
        "high20": r(max(hh[-20:])), "low20": r(min(ll[-20:])),
        "high52": r(max(hh[-250:])) if len(hh) >= 120 else None, "low52": r(min(ll[-250:])) if len(ll) >= 120 else None,
        "trend": trend, "sr": {k: [r(x) for x in v] for k, v in sr.items()},
        "pivots": {k: r(v) for k, v in ind.pivots(hh[-1], ll[-1], cl[-1]).items()},
        "unusual": unusual, "problems": Q.validate(daily),
    })
    return snap


def scan(ctx, need_intraday: bool, index_daily=None) -> tuple[list[dict], dict]:
    stocks = ctx.cfg.stocks()
    index_closes = completed(index_daily, ctx).c if index_daily is not None and index_daily.ok else None

    def fetch(ticker):
        d = yahoo.chart(ctx.client, ticker, "2y", "1d", events=True)
        i = yahoo.chart(ctx.client, ticker, "5d", "5m") if need_intraday else None
        return ticker, d, i

    results = parallel_map(fetch, list(stocks), ctx.workers)
    snaps, series = [], {}
    for ticker, d, i in results:
        series[ticker] = {"daily": d, "intra": i}
        try:
            snaps.append(snapshot(ticker, stocks[ticker], d, i, ctx, index_closes))
        except Exception as e:  # tek hisse hatası tüm raporu durdurmasın
            snaps.append({"ticker": ticker, "q_daily": Q.UNAVAILABLE, "q_daily_note": f"analiz hatası: {e}",
                          "name": ticker, "sector": stocks[ticker].get("sector"), "watch": stocks[ticker].get("watch")})
    return snaps, series


def breadth(snaps: list[dict]) -> dict:
    ch = [s["chg"] for s in snaps if s.get("chg") is not None]
    adv = sum(1 for x in ch if x > 0)
    dec = sum(1 for x in ch if x < 0)
    return {"adv": adv, "dec": dec, "flat": len(ch) - adv - dec, "total": len(ch)}


def movers(snaps: list[dict], n: int = 5) -> tuple[list, list]:
    ok = [s for s in snaps if s.get("chg") is not None and s.get("liq") != "düşük"]
    ok.sort(key=lambda s: s["chg"], reverse=True)
    return ok[:n], list(reversed(ok[-n:])) if len(ok) >= n else list(reversed(ok))


def unusual_volume(snaps: list[dict], n: int = 6) -> list:
    ok = [s for s in snaps if (s.get("relvol") or 0) >= 1.8 and s.get("chg") is not None]
    ok.sort(key=lambda s: s["relvol"], reverse=True)
    return ok[:n]


def sector_strength_from_stocks(snaps: list[dict]) -> list[dict]:
    by = {}
    for s in snaps:
        if s.get("chg") is None:
            continue
        by.setdefault(s.get("sector") or "Diğer", []).append(s["chg"])
    rows = [{"sector": k, "avg_chg": r(sum(v) / len(v)), "n": len(v)} for k, v in by.items() if len(v) >= 2]
    rows.sort(key=lambda x: -x["avg_chg"])
    return rows
