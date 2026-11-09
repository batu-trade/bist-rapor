"""Swing analizi (yaklaşık 2–20 işlem günü): günlük + haftalık eğilim, göreceli güç, hacim teyidi."""
from __future__ import annotations

from . import fmt
from . import indicators as ind
from . import quality as Q
from .market import completed
from .risk import RiskConfig, position_size, risk_reward
from .tz import to_ist
from .util import r

SETUP_TR = {
    "breakout": "Kırılım (20 günlük zirve)",
    "pullback": "Yükselen trendde geri çekilme",
    "retest": "Kırılım sonrası yeniden test",
}
SETUP_EXPLAIN = {
    "breakout": "Fiyat son 20 günün en yüksek seviyesini hacimle aştı. Yeni bir yükseliş dalgasının başlangıcı olabilir.",
    "pullback": "Ana eğilimi yukarı olan hisse, ortalamasına doğru geri çekildi. Trend sürerse görece düşük riskli giriş bölgesi sunabilir.",
    "retest": "Hisse kısa süre önce bir direnci kırdı ve şimdi o seviyeyi destek olarak test ediyor. Klasik 'kır ve test et' yapısı.",
}


def weekly_trend(daily) -> str:
    wk = ind.weekly(daily.t, daily.o, daily.h, daily.l, daily.c, daily.v, lambda t: to_ist(t).date())
    closes = [w[3] for w in wk]
    if len(closes) < 32:
        return "belirsiz"
    e10, e30 = ind.last(ind.ema(closes, 10)), ind.last(ind.ema(closes, 30))
    if closes[-1] > e10 > e30:
        return "yukarı"
    if closes[-1] < e10 < e30:
        return "aşağı"
    return "yatay"


def analyze(snap: dict, daily, ctx, sector_ret20: dict, index_ret20: float | None, cfg_r: RiskConfig,
            capital: float) -> dict | None:
    if not Q.at_least(snap.get("q_daily", Q.UNAVAILABLE), Q.INCOMPLETE) or snap.get("price") is None:
        return None
    if snap.get("q_daily") == Q.INCOMPLETE and "sıçrama" in (snap.get("q_daily_note") or ""):
        return None  # düzeltilmemiş bölünme olabilir: teknik seviyeler güvenilmez
    comp = completed(daily, ctx)
    cl, hh, ll, vv = comp.c, comp.h, comp.l, comp.v
    if len(cl) < 120:
        return None
    price = snap["price"]
    atr = snap.get("atr")
    if not atr:
        return None
    e20, e50 = snap.get("ema20"), snap.get("ema50")
    e200 = snap.get("ema200")
    rsi = snap.get("rsi") or 50
    adx = snap.get("adx") or 0
    wtrend = weekly_trend(comp)
    avg_vol20 = sum(vv[-21:-1]) / 20 if len(vv) > 21 else None
    vol_ratio = (vv[-1] / avg_vol20) if avg_vol20 else None
    prior_high20 = max(hh[-21:-1])
    up_trend = e50 and e200 and cl[-1] > e50 > e200
    setups = []

    # Kırılım: dünkü (tamamlanmış) kapanış önceki 20 günün zirvesini aştı
    if cl[-1] > prior_high20 and (vol_ratio or 0) >= 1.3 and adx >= 18:
        lvl = prior_high20
        chase = price > lvl + 0.8 * atr
        lo, hi = (lvl, lvl + 0.5 * atr)
        stop = lvl - 1.2 * atr
        setups.append(("breakout", lo, hi, stop, chase))
    # Kırılım sonrası yeniden test: son 3-10 gün içinde 20g zirve kırıldı, fiyat o seviyeye yakın
    for back in range(3, 11):
        if len(cl) < back + 22:
            break
        ph = max(hh[-back - 21:-back - 1])
        if cl[-back - 1] > ph and abs(price - ph) <= 0.8 * atr and price >= ph - 0.5 * atr:
            setups.append(("retest", ph - 0.3 * atr, ph + 0.3 * atr, ph - 1.3 * atr, False))
            break
    # Geri çekilme: yükselen trend, fiyat EMA20/EMA50'ye yakın, RSI ılımlı
    if up_trend and 38 <= rsi <= 58:
        for ma, name in ((e20, "EMA20"), (e50, "EMA50")):
            if ma and abs(price - ma) <= 1.0 * atr:
                low10 = min(ll[-10:])
                stop = min(low10, ma - 1.2 * atr) - 0.2 * atr
                stop = max(stop, price - 3 * atr)
                setups.append(("pullback", ma - 0.3 * atr, ma + 0.3 * atr, stop, False))
                break
    if not setups:
        return None

    best = None
    for kind, lo, hi, stop, chase in setups:
        entry = (lo + hi) / 2
        risk = entry - stop
        if risk <= 0:
            continue
        if risk < 1.0 * atr:
            stop = entry - 1.0 * atr
            risk = entry - stop
        t1 = entry + 2 * risk
        t2 = entry + 3.5 * risk
        notes = []
        h52 = snap.get("high52")
        if h52 and entry < h52 < t1 and (h52 - entry) / risk >= 1.5:
            t1 = h52
            notes.append(f"Hedef 1, 52 haftalık zirve ({fmt.num(h52, 2)}) ile sınırlandı")
        rr = risk_reward(entry, stop, t1)
        if rr is None:
            continue
        score = 0.0
        reasons, risks = [], []
        if up_trend:
            score += 3
            reasons.append("Günlük eğilim yukarı (fiyat > EMA50 > EMA200)")
        elif e50 and cl[-1] > e50:
            score += 1.5
            reasons.append("Fiyat 50 günlük ortalamanın üzerinde")
        else:
            risks.append("Ana eğilim yukarı değil")
        if wtrend == "yukarı":
            score += 2
            reasons.append("Haftalık grafikte de eğilim yukarı")
        elif wtrend == "aşağı":
            score -= 1
            risks.append("Haftalık eğilim aşağı")
        rs20, rs60 = snap.get("rs20"), snap.get("rs60")
        if rs20 is not None and rs20 > 0:
            score += 1
            reasons.append(f"Son 20 günde BIST 100'den {fmt.signed(rs20, 1)} puan daha iyi")
        if rs60 is not None and rs60 > 0:
            score += 1
        if rs20 is not None and rs20 < -5:
            risks.append(f"Son 20 günde endeksin {fmt.num(abs(rs20), 1)} puan gerisinde")
        if vol_ratio and vol_ratio >= 1.3:
            score += min(2, vol_ratio - 0.3)
            reasons.append(f"Son gün hacmi ortalamanın {fmt.num(vol_ratio, 1)} katı (hacim teyidi)")
        if adx >= 20:
            score += 1
            reasons.append(f"ADX {fmt.num(adx, 0)}: eğilim güçlü")
        hist, hist_prev = snap.get("macd_hist"), snap.get("macd_hist_prev")
        if hist is not None and hist_prev is not None and hist > hist_prev:
            score += 0.5
            reasons.append("MACD momentumu iyileşiyor")
        if rsi > 72:
            score -= 1.5
            risks.append(f"RSI {fmt.num(rsi, 0)}: kısa vadede aşırı alım")
        sr20 = sector_ret20.get(snap.get("si"))
        if sr20 is not None and index_ret20 is not None and sr20 > index_ret20:
            score += 1
            reasons.append("Sektörü endeksten güçlü")
        score += min(2, max(0, rr - 1.5))
        if chase:
            risks.append("Fiyat kırılım seviyesinden uzaklaştı: kovalamak yerine giriş bölgesine geri çekilme beklenebilir")
            score -= 1
        if snap.get("liq") == "düşük":
            risks.append("Düşük likidite")
            score -= 1
        risks += notes
        cand = (score, kind, lo, hi, entry, stop, t1, t2, rr, reasons, risks)
        if best is None or cand[0] > best[0]:
            best = cand
    if best is None:
        return None
    score, kind, lo, hi, entry, stop, t1, t2, rr, reasons, risks = best
    min_rr = float(ctx.cfg.get("swing", "min_rr", default=1.8))
    if rr < min_rr:
        return None
    days = max(2, min(20, round((t1 - entry) / (0.5 * atr))))
    grade = "A" if score >= 9 else ("B" if score >= 6 else "C")
    if snap.get("q_daily") == Q.DELAYED:
        risks.append("Bugünkü günlük mum henüz kapanmadı; seviyeler kapanışta değişebilir")
    if not risks:
        risks.append("Genel piyasada sert düşüş veya şirkete özel olumsuz bir haber kurulumu kolayca bozabilir")
    size = position_size(capital, entry, stop, cfg_r, snap.get("avg_tl_vol20"))
    return {
        "ticker": snap["ticker"], "name": snap.get("name"), "sector": snap.get("sector"), "kind": "swing",
        "setup": kind, "setup_tr": SETUP_TR[kind], "explain": SETUP_EXPLAIN[kind],
        "price": r(price), "time": snap.get("time"), "quality": snap.get("q_daily"),
        "entry_low": r(lo), "entry_high": r(hi), "entry": r(entry), "stop": r(stop), "t1": r(t1), "t2": r(t2),
        "rr": r(rr, 2), "hold_days": f"{max(2, days - 3)}–{min(20, days + 4)} işlem günü",
        "score": r(score, 1), "grade": grade, "weekly_trend": wtrend, "reasons": reasons, "risks": risks,
        "invalidation": f"Günlük kapanış {fmt.num(stop, 2)} altında olursa veya fiyat EMA50 ({fmt.num((e50 or 0), 2)}) altında iki gün kapanırsa kurulum bozulur",
        "size_example": size,
    }
