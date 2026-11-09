"""Gün içi analiz: 5 dakikalık (gecikmeli) mumlarla kurulum tespiti.

Dürüstlük kuralları:
  * Veri kalitesi 'gecikmeli' veya 'güvenilir' değilse sinyal ÜRETİLMEZ.
  * Gecikmeli veride güven en fazla 'orta' olabilir.
  * Sinyaller alım-satım talimatı değil, analitik senaryodur.
Yalnızca alış yönlü kurulumlar üretilir (BIST'te açığa satış küçük yatırımcı
için genellikle uygun değildir); zayıf hisseler "satış baskısı uyarısı" olarak listelenir.
"""
from __future__ import annotations

from . import fmt
import datetime as dt

from . import indicators as ind
from . import quality as Q
from .risk import RiskConfig, position_size, risk_reward
from .tz import to_ist
from .util import r

STRATEGY_TR = {
    "orb": "Açılış aralığı kırılımı",
    "vwap_reclaim": "VWAP geri alımı",
    "pullback": "Trend içi geri çekilme",
    "momentum": "Momentum devamı",
    "reversal": "Aşırı satımdan dönüş",
}

STRATEGY_EXPLAIN = {
    "orb": "Fiyat, seansın ilk 30 dakikasındaki en yüksek seviyeyi hacimle yukarı kırdı. Bu genellikle gün içi alıcıların güçlü olduğunu gösterir.",
    "vwap_reclaim": "Fiyat gün içinde ortalama işlem fiyatının (VWAP) altına inmiş, sonra tekrar üzerine çıkmış. Alıcıların kontrolü geri aldığına işaret edebilir.",
    "pullback": "Yükselen bir günde fiyat kısa ortalamaya kadar geri çekildi ve tutunuyor. Trend devam ederse düşük riskli bir giriş bölgesi sunabilir.",
    "momentum": "Hisse güçlü yükseliyor, günün zirvesine yakın ve hacim normalin üzerinde. Güçlü momentum bazen devam eder ama geç kalma riski yüksektir.",
    "reversal": "Hisse kısa vadede aşırı satılmış (RSI düşük) ve bir destek seviyesinden tepki veriyor. Ters yönlü işlem olduğu için risklidir.",
}


def _session_bars(intra, day: dt.date):
    return intra.only_date(day)


def analyze(snap: dict, intra, ctx, market_chg: float | None, cfg_r: RiskConfig, capital: float) -> tuple[list, dict]:
    """Bir hisse için gün içi sinyaller ve durum özeti döndürür."""
    status = {"ticker": snap["ticker"], "analyzed": False}
    q = snap.get("q_intra", Q.UNAVAILABLE)
    if intra is None or not Q.at_least(q, Q.DELAYED):
        status["reason"] = snap.get("q_intra_note", "gün içi veri yok")
        return [], status
    today = _session_bars(intra, ctx.today)
    if len(today) < 3:
        status["reason"] = "yetersiz mum"
        return [], status
    status["analyzed"] = True
    cl_all = intra.c
    e9_all, e20_all = ind.ema(cl_all, 9), ind.ema(cl_all, 20)
    atr_all = ind.atr(intra.h, intra.l, intra.c, 14)
    rsi_all = ind.rsi(cl_all, 14)
    off = len(intra) - len(today)
    e9, e20 = e9_all[off:], e20_all[off:]
    rsi = rsi_all[off:]
    atr5 = ind.last(atr_all)
    vw = ind.vwap(today.h, today.l, today.c, today.v)
    if not atr5 or atr5 <= 0 or vw[-1] is None:
        status["reason"] = "gösterge hesaplanamadı"
        status["analyzed"] = False
        return [], status
    c = today.c[-1]
    v_last = vw[-1]
    relvol = snap.get("relvol") or 0
    day_chg = snap.get("chg") or 0
    day_hi, day_lo = max(today.h), min(today.l)
    times = [to_ist(t) for t in today.t]
    or_end = times[0].replace(hour=10, minute=30)
    or_idx = [i for i, t in enumerate(times) if t < or_end]
    or_done = times[-1] >= or_end and len(or_idx) >= 3
    or_hi = max(today.h[i] for i in or_idx) if or_idx else None
    or_lo = min(today.l[i] for i in or_idx) if or_idx else None
    piv = snap.get("pivots") or {}
    sr = snap.get("sr") or {}
    res_above = [x for x in (sr.get("resistances") or []) if x and x > c]
    sup_below = [x for x in (sr.get("supports") or []) if x and x < c]
    daily_up = snap.get("ema50") and snap.get("price") and snap["price"] > snap["ema50"]
    status.update({
        "vwap": r(v_last), "above_vwap": c > v_last, "ema9": r(e9[-1]), "ema20": r(e20[-1]),
        "rsi5": r(ind.last(rsi), 1), "atr5": r(atr5, 3), "or_high": r(or_hi), "or_low": r(or_lo),
        "or_done": or_done, "day_high": r(day_hi), "day_low": r(day_lo), "last": r(c),
        "last_time": times[-1].isoformat(),
    })

    cands = []

    def add(strategy, entry_lo, entry_hi, stop, reasons, risks, base_score):
        entry = (entry_lo + entry_hi) / 2
        if stop >= entry:
            return
        risk = entry - stop
        if risk < 0.3 * atr5:
            stop = entry - 0.6 * atr5
            risk = entry - stop
        t1 = entry + 1.5 * risk
        t2 = entry + 2.5 * risk
        note_t = None
        if res_above and res_above[0] < t1 and (res_above[0] - entry) / risk >= 1.0:
            note_t = f"Yakın direnç {fmt.num(res_above[0], 2)}: hedef 1 bu seviyeye çekildi"
            t1 = res_above[0]
        rr = risk_reward(entry, stop, t1)
        cands.append({
            "strategy": strategy, "entry_low": entry_lo, "entry_high": entry_hi, "entry": entry, "stop": stop,
            "t1": t1, "t2": t2, "rr": rr, "reasons": reasons, "risks": risks + ([note_t] if note_t else []),
            "base": base_score,
        })

    # 1) Açılış aralığı kırılımı
    if or_done and or_hi and c > or_hi and c > v_last and relvol >= 1.3:
        stop = min((or_hi + or_lo) / 2, v_last) - 0.1 * atr5
        add("orb", or_hi, or_hi + 0.25 * atr5, stop,
            [f"İlk 30 dk zirvesi {fmt.num(or_hi, 2)} yukarı kırıldı", f"Fiyat VWAP ({fmt.num(v_last, 2)}) üzerinde",
             f"Hacim normalin {fmt.num(relvol, 1)} katı"],
            ["Kırılım sonrası fiyat aralığın içine geri dönerse kırılım başarısız sayılır"], 3)
    # 2) VWAP geri alımı
    below_before = any(today.c[i] < vw[i] for i in range(max(0, len(today) - 12), len(today) - 2) if vw[i])
    if (len(today) >= 6 and below_before and today.c[-1] > v_last and today.c[-2] > (vw[-2] or 0)
            and e9[-1] and e20[-1] and e9[-1] >= e20[-1] * 0.999 and relvol >= 1.0):
        stop = min(today.l[-6:]) - 0.1 * atr5
        add("vwap_reclaim", v_last, v_last + 0.2 * atr5, stop,
            [f"Fiyat VWAP'ın ({fmt.num(v_last, 2)}) altından tekrar üzerine çıktı", "Kısa ortalama (EMA9) yukarı döndü"],
            ["VWAP'ın tekrar altına sarkma, sinyali geçersiz kılar"], 2)
    # 3) Trend içi geri çekilme
    if (e9[-1] and e20[-1] and c > v_last and e9[-1] > e20[-1] and day_chg > 0.5
            and min(today.l[-3:]) <= max(e20[-1], v_last) + 0.3 * atr5 and c > e20[-1]
            and 40 <= (ind.last(rsi) or 50) <= 62):
        stop = min(e20[-1], v_last) - 0.6 * atr5
        add("pullback", e20[-1], c, stop,
            ["Yükselen günde kısa ortalamaya (EMA20) geri çekilme", f"RSI {fmt.num(ind.last(rsi), 0)}: aşırı alım yok"],
            ["Fiyat EMA20 ve VWAP altına inerse trend bozulur"], 2)
    # 4) Momentum devamı
    if day_chg >= 2 and c >= day_hi - 0.3 * atr5 and relvol >= 1.8 and (ind.last(rsi) or 50) < 78:
        stop = max(v_last - 0.1 * atr5, c - 1.5 * atr5)
        add("momentum", c - 0.3 * atr5, c, stop,
            [f"Gün içi {fmt.pct(day_chg, 1)} yükseliş, zirveye yakın", f"Hacim normalin {fmt.num(relvol, 1)} katı"],
            ["Geç giriş riski: yükselişin büyük kısmı gerçekleşmiş olabilir", "Kâr satışları sert geri çekilme yaratabilir"], 1)
    # 5) Aşırı satımdan dönüş
    rs6 = [x for x in rsi[-6:] if x is not None]
    near_sup = any(abs(c / s - 1) < 0.01 for s in [piv.get("S1"), snap.get("low20")] + sup_below[:1] if s)
    if rs6 and min(rs6) < 30 and (ind.last(rsi) or 0) > 35 and today.c[-1] > today.h[-2] and near_sup:
        stop = min(today.l[-6:]) - 0.2 * atr5
        add("reversal", c - 0.2 * atr5, c, stop,
            ["5 dakikalık RSI 30'un altından yukarı döndü", "Fiyat bir destek seviyesine yakın"],
            ["Ana eğilime karşı işlem: başarı oranı genelde düşüktür"], 1)

    min_rr = float(ctx.cfg.get("intraday", "min_rr", default=1.5))
    signals = []
    for cd in cands:
        if cd["rr"] is None or cd["rr"] < min_rr:
            continue
        score = cd["base"] + min(relvol, 3) + (1 if daily_up else 0) + (1 if (market_chg or 0) > 0 else 0)
        conf = "orta" if score >= 5 else "düşük"
        if q == Q.RELIABLE and score >= 6:
            conf = "yüksek"
        risks = list(cd["risks"])
        if q == Q.DELAYED:
            risks.append(f"Veri ~{fmt.num(snap.get('delay_min') or 15, 0)} dk gecikmeli: gerçek fiyat şu an farklı olabilir")
        if not daily_up:
            risks.append("Günlük grafikte ana eğilim zayıf (fiyat 50 günlük ortalamanın altında)")
        if (market_chg or 0) < -0.5:
            risks.append("Genel piyasa düşüşte: bireysel yükselişler kolay bozulabilir")
        if snap.get("liq") == "düşük":
            risks.append("Düşük likidite: alış-satış farkı ve kayma yüksek olabilir")
        if not risks:
            risks.append("Gün içi hareketler hızlı tersine dönebilir; stop seviyesine uyulmazsa zarar büyüyebilir")
        size = position_size(capital, cd["entry"], cd["stop"], cfg_r, snap.get("avg_tl_vol20"))
        signals.append({
            "ticker": snap["ticker"], "name": snap.get("name"), "sector": snap.get("sector"),
            "kind": "intraday", "strategy": cd["strategy"], "strategy_tr": STRATEGY_TR[cd["strategy"]],
            "explain": STRATEGY_EXPLAIN[cd["strategy"]], "direction": "alış (long)",
            "price": r(c), "time": times[-1].isoformat(), "quality": q, "delay_min": snap.get("delay_min"),
            "entry_low": r(cd["entry_low"]), "entry_high": r(cd["entry_high"]), "entry": r(cd["entry"]),
            "stop": r(cd["stop"]), "t1": r(cd["t1"]), "t2": r(cd["t2"]), "rr": r(cd["rr"], 2),
            "confidence": conf, "score": r(score, 2), "reasons": cd["reasons"], "risks": risks,
            "invalidation": f"Fiyat {fmt.num(cd['stop'], 2)} altına inerse senaryo geçersiz",
            "size_example": size, "liq": snap.get("liq"),
        })
    signals.sort(key=lambda s: -s["score"])
    # Satış baskısı uyarısı (işlem önerisi değil)
    if c < v_last and e9[-1] and e20[-1] and e9[-1] < e20[-1] and day_chg <= -2 and relvol >= 1.5:
        status["weakness"] = (f"Satış baskısı: fiyat VWAP altında, gün içi {fmt.pct(day_chg, 1)}, hacim normalin "
                              f"{fmt.num(relvol, 1)} katı. Bu hissede yeni alım için acele etmemek mantıklı olabilir.")
    return signals[:1], status


def evaluate_signal(sig: dict, intra, since: dt.datetime) -> dict:
    """Bir sinyalin sonrasında ne olduğunu 5 dk mumlarla kontrol eder (stop önce varsayımı: muhafazakâr)."""
    if intra is None or not intra.ok:
        return {"result": "veri yok"}
    stop, t1, t2 = sig.get("stop"), sig.get("t1"), sig.get("t2")
    entry = sig.get("entry")
    outcome = None
    for t, h, l in zip(intra.t, intra.h, intra.l):
        if to_ist(t) <= since or to_ist(t).date() != since.date():
            continue
        if l <= stop:
            outcome = ("stop", stop, to_ist(t))
            break
        if t2 and h >= t2:
            outcome = ("hedef 2", t2, to_ist(t))
            break
        if h >= t1:
            outcome = ("hedef 1", t1, to_ist(t))
            break
    day = intra.only_date(since.date())
    last = day.c[-1] if len(day) else None
    if outcome:
        res, px, when = outcome
        return {"result": res, "price": r(px), "time": when.isoformat(),
                "pct": r((px / entry - 1) * 100) if entry else None}
    return {"result": "açık kaldı", "price": r(last), "pct": r((last / entry - 1) * 100) if (entry and last) else None}
