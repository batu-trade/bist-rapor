"""Piyasa geneli: BIST 100 / BIST 30, sektör endeksleri, küresel piyasalar, kur."""
from __future__ import annotations

from . import fmt
import datetime as dt

from . import indicators as ind
from . import quality as Q
from . import yahoo
from .tz import to_ist
from .util import parallel_map, r


def completed(series, ctx):
    """Seans bitmediyse bugünkü (yarım) günlük mumu çıkarır."""
    if series.ok and series.dates()[-1] == ctx.today and ctx.phase in ("pre", "open"):
        return series.before_date(ctx.today)
    return series


def trend_label(close, e20, e50, e200) -> str:
    if None in (close, e50):
        return "belirsiz"
    if e200 is not None and close > e50 > e200:
        return "yükselen"
    if e200 is not None and close < e50 < e200:
        return "düşen"
    if close > e50:
        return "toparlanma / yatay-yukarı"
    return "zayıf / yatay-aşağı"


TREND_EXPLAIN = {
    "yükselen": "Fiyat 50 ve 200 günlük ortalamaların üzerinde: ana eğilim yukarı.",
    "düşen": "Fiyat 50 ve 200 günlük ortalamaların altında: ana eğilim aşağı.",
    "toparlanma / yatay-yukarı": "Fiyat 50 günlük ortalamanın üzerinde ama uzun vadeli eğilim henüz net değil.",
    "zayıf / yatay-aşağı": "Fiyat 50 günlük ortalamanın altında: kısa-orta vadede zayıf görünüm.",
    "belirsiz": "Yeterli geçmiş veri yok.",
}


def index_overview(code: str, name: str, daily, intra, ctx) -> dict:
    o_s, c_s = ctx.session
    dq, dnote = Q.assess_daily(daily, ctx.now, ctx.expected_daily_last, o_s, c_s, min_len=200, is_index=True)
    out = {"code": code, "name": name, "quality": dq, "quality_note": dnote}
    if not daily.ok:
        return out
    dc = yahoo.daily_change(daily)
    comp = completed(daily, ctx)
    cl, hh, ll = comp.c, comp.h, comp.l
    e20, e50, e200 = (ind.last(ind.ema(cl, n)) for n in (20, 50, 200))
    rsi = ind.last(ind.rsi(cl))
    _, _, hist = ind.macd(cl)
    adx, _, _ = ind.adx(hh, ll, cl)
    price = dc["price"]
    trend = trend_label(cl[-1] if cl else None, e20, e50, e200)
    out.update({
        "price": r(price), "prev": r(dc["prev"]), "chg": r(dc["chg"]), "time": dc["time"].isoformat() if dc["time"] else None,
        "ema20": r(e20), "ema50": r(e50), "ema200": r(e200), "rsi": r(rsi, 1),
        "macd_hist": r(ind.last(hist), 3), "adx": r(ind.last(adx), 1), "trend": trend,
        "trend_explain": TREND_EXPLAIN.get(trend, ""),
        "ret5": r(ind.pct_change(cl[-1], cl[-6]) if len(cl) > 6 else None),
        "ret20": r(ind.pct_change(cl[-1], cl[-21]) if len(cl) > 21 else None),
    })
    if cl:
        out["pivots"] = {k: r(v) for k, v in ind.pivots(hh[-1], ll[-1], cl[-1]).items()}
        out["sr"] = {k: [r(x) for x in v] for k, v in ind.support_resistance(hh, ll, cl, price).items()}
        out["last_close_date"] = comp.dates()[-1].isoformat()
    if intra is not None:
        iq, inote, age = Q.assess_intraday(intra, ctx.now, o_s, c_s, min_bars=2)
        out.update({"intra_quality": iq, "intra_note": inote, "delay_min": r(age, 0)})
        today = intra.only_date(ctx.today)
        if len(today):
            op = today.o[0]
            out.update({
                "open": r(op), "day_high": r(max(today.h)), "day_low": r(min(today.l)),
                "since_open": r(ind.pct_change(today.c[-1], op)),
                "gap": r(ind.pct_change(op, dc["prev"])) if dc["prev"] else None,
                "intra_last": r(today.c[-1]), "intra_last_time": today.last_time.isoformat(),
                "bars_today": len(today),
            })
    return out


def change_table(series_by_code: dict, names: dict, ctx) -> list[dict]:
    rows = []
    for code, s in series_by_code.items():
        name = names.get(code, code)
        if not s.ok:
            rows.append({"code": code, "name": name, "quality": Q.UNAVAILABLE, "chg": None})
            continue
        dc = yahoo.daily_change(s)
        cl = s.c
        age_days = (ctx.now - dc["time"]).total_seconds() / 86400 if dc["time"] else None
        q = Q.RELIABLE
        if age_days is not None and age_days > 4:
            q = Q.STALE
        rows.append({
            "code": code, "name": name, "price": r(dc["price"], 4 if dc["price"] and dc["price"] < 10 else 2),
            "chg": r(dc["chg"]), "time": dc["time"].isoformat() if dc["time"] else None,
            "ret5": r(ind.pct_change(cl[-1], cl[-6]) if len(cl) > 6 else None),
            "ret20": r(ind.pct_change(cl[-1], cl[-21]) if len(cl) > 21 else None),
            "quality": q,
        })
    return rows


def fetch_market(ctx, need_intraday: bool) -> dict:
    cfg = ctx.cfg
    client = ctx.client
    idx = cfg.universe.get("indices", {"XU100": "BIST 100", "XU030": "BIST 30"})
    sect = cfg.universe.get("sector_indices", {})
    glob = cfg.get("global_markets", default=[]) or []

    jobs = []
    for code in idx:
        jobs.append(("idx_d", code, code, "2y", "1d"))
        if need_intraday:
            jobs.append(("idx_i", code, code, "5d", "5m"))
    for code in sect:
        jobs.append(("sec", code, code, "3mo", "1d"))
    for sym, _ in glob:
        jobs.append(("glb", sym, sym, "1mo", "1d"))

    def run(job):
        kind, key, sym, rng, iv = job
        return kind, key, yahoo.chart(client, sym, rng, iv)

    results = parallel_map(run, jobs, ctx.workers)
    got = {"idx_d": {}, "idx_i": {}, "sec": {}, "glb": {}}
    for kind, key, s in results:
        got[kind][key] = s

    indices = []
    for code, name in idx.items():
        indices.append(index_overview(code, name, got["idx_d"][code], got["idx_i"].get(code), ctx))
    sectors = change_table(got["sec"], sect, ctx)
    sectors.sort(key=lambda x: (x["chg"] is None, -(x["chg"] or 0)))
    gnames = {s: n for s, n in glob}
    global_rows = change_table(got["glb"], gnames, ctx)
    return {
        "indices": indices,
        "sectors": sectors,
        "global": global_rows,
        "_series": got,
    }


def market_direction(ix: dict, breadth: dict | None) -> tuple[str, str]:
    """Basit yön yorumu: ('yukarı'|'aşağı'|'yatay', açıklama)."""
    chg = ix.get("chg")
    if chg is None:
        return "bilinmiyor", "Endeks verisi alınamadı."
    adv = (breadth or {}).get("adv", 0)
    dec = (breadth or {}).get("dec", 0)
    tot = adv + dec
    ratio = adv / tot if tot else 0.5
    if chg > 0.5 and ratio >= 0.55:
        return "yukarı", f"Endeks {fmt.pct(chg, 2)} ve yükselen hisse oranı %{fmt.num(ratio * 100, 0)}: alıcılar baskın."
    if chg < -0.5 and ratio <= 0.45:
        return "aşağı", f"Endeks {fmt.pct(chg, 2)} ve yükselen hisse oranı yalnızca %{fmt.num(ratio * 100, 0)}: satıcılar baskın."
    if chg > 0.5:
        return "yukarı (dar tabanlı)", f"Endeks {fmt.pct(chg, 2)} yükselse de hisselerin çoğu katılmıyor; yükseliş birkaç büyük hisseye dayanıyor olabilir."
    if chg < -0.5:
        return "aşağı (dar tabanlı)", f"Endeks {fmt.pct(chg, 2)} düşüyor ama hisselerin önemli bir kısmı direniyor."
    return "yatay", f"Endeks {fmt.pct(chg, 2)}: belirgin bir yön yok."


def fx_from_tcmb(client) -> dict:
    """TCMB gösterge kurları (resmî, ücretsiz; günde bir kez ~15:30'da yayımlanır)."""
    import xml.etree.ElementTree as ET
    try:
        root = ET.fromstring(client.text("https://www.tcmb.gov.tr/kurlar/today.xml"))
    except Exception as e:
        return {"error": str(e)}
    out = {"date": root.attrib.get("Tarih"), "rates": {}}
    for cur in root.findall("Currency"):
        code = cur.attrib.get("CurrencyCode") or cur.attrib.get("Kod")
        if code in ("USD", "EUR", "GBP"):
            try:
                out["rates"][code] = float((cur.findtext("ForexSelling") or "").strip())
            except ValueError:
                pass
    return out


def age_text(ts_iso: str | None, now: dt.datetime) -> str:
    if not ts_iso:
        return "—"
    d = dt.datetime.fromisoformat(ts_iso)
    mins = (now - d).total_seconds() / 60
    if mins < 90:
        return f"{fmt.num(mins, 0)} dk önce"
    if mins < 60 * 36:
        return f"{fmt.num(mins / 60, 0)} saat önce"
    return f"{fmt.num(mins / 1440, 0)} gün önce"
