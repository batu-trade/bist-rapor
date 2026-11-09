"""Dört günlük rapor: 09:45 açılış öncesi, 10:15 açılış sonrası, 14:00 gün ortası, 18:15 kapanış."""
from __future__ import annotations

import datetime as dt
import time

from . import blocks as B
from . import fmt
from . import fundamentals as F
from . import intraday as I
from . import market as M
from . import news as N
from . import paper as P
from . import quality as Q
from . import scanner as S
from . import swing as SW
from . import yahoo
from .risk import RiskConfig
from .tz import SLOTS, slot_time
from .util import load_json, r, save_json

DISCLAIMER = ("Bu rapor yatırım tavsiyesi değildir. Kişisel kullanım amaçlı, ücretsiz ve gecikmeli verilerle otomatik "
              "üretilmiş analitik bir özettir. Seviyeler ve senaryolar alım-satım talimatı değildir; kararlarınızı "
              "kendi araştırmanız ve gerekirse lisanslı bir yatırım danışmanıyla verin. Simülasyon sonuçları gerçek "
              "getiri değildir.")


def report_path(data_dir, day: dt.date, slot: str):
    return data_dir / "reports" / day.isoformat() / f"{slot}.json"


def load_report(data_dir, day: dt.date, slot: str) -> dict | None:
    return load_json(report_path(data_dir, day, slot))


# ---------------------------------------------------------------------------
# Veri toplama
# ---------------------------------------------------------------------------

def gather(ctx, slot: str, refresh_fund: str | None = None) -> dict:
    need_intra = slot != "premarket"
    t0 = time.time()
    mk = M.fetch_market(ctx, need_intra)
    xu100_daily = mk["_series"]["idx_d"].get("XU100")
    snaps, series = S.scan(ctx, need_intra, xu100_daily)
    by_t = {s["ticker"]: s for s in snaps}
    br = S.breadth(snaps)
    xu = next((x for x in mk["indices"] if x["code"] == "XU100"), {})
    cfg_r = RiskConfig.from_settings(ctx.cfg.settings)
    paper_cap = float(ctx.cfg.get("paper_capital_tl", default=100000))
    split = ctx.cfg.get("capital_split_pct", default={}) or {}
    tot = sum(split.values()) or 100
    cap_intra = paper_cap * split.get("gun_ici", 10) / tot
    cap_swing = paper_cap * split.get("swing", 20) / tot

    # Gün içi
    intra_sigs, intra_status, weak = [], {}, []
    if need_intra:
        for s in snaps:
            ser = series.get(s["ticker"], {}).get("intra")
            sigs, st = I.analyze(s, ser, ctx, xu.get("chg"), cfg_r, cap_intra)
            intra_status[s["ticker"]] = st
            intra_sigs += sigs
            if st.get("weakness"):
                weak.append({"ticker": s["ticker"], "text": st["weakness"]})
        intra_sigs.sort(key=lambda x: -x["score"])
        intra_sigs = intra_sigs[: int(ctx.cfg.get("intraday", "max_signals", default=5))]

    # Swing
    sector_ret20 = {row["code"]: row.get("ret20") for row in mk["sectors"]}
    swing = []
    for s in snaps:
        try:
            c = SW.analyze(s, series[s["ticker"]]["daily"], ctx, sector_ret20, xu.get("ret20"), cfg_r, cap_swing)
        except Exception:
            c = None
        if c:
            swing.append(c)
    swing.sort(key=lambda x: -x["score"])
    swing = swing[: int(ctx.cfg.get("swing", "max_candidates", default=8))]

    # Temel analiz (önbellekten; kapanış ve açılış öncesinde eskiyenleri yenile)
    fund_cache = None
    try:
        if slot in ("close", "premarket") or refresh_fund:
            fund_cache = F.refresh_cache(ctx, {}, force_all=(refresh_fund == "all"))
        else:
            fund_cache = load_json(ctx.cfg.data_dir / "cache" / "fundamentals.json", {}) or {}
        fund = F.analyze_all(ctx, fund_cache, by_t)
    except Exception as e:
        fund = []
        ctx.fund_error = str(e)

    # Haberler: açılış öncesi için dünkü kapanıştan beri; diğerleri için son 24 saat / sabahtan beri
    if slot == "premarket":
        prev = ctx.cal.previous_trading_day(ctx.today)
        since = dt.datetime(prev.year, prev.month, prev.day, 18, 10, tzinfo=ctx.now.tzinfo)
    elif slot == "close":
        since = ctx.now - dt.timedelta(hours=24)
    else:
        since = ctx.now - dt.timedelta(hours=16)
    nw = N.collect(ctx, since, set(by_t))
    fx = M.fx_from_tcmb(ctx.client)
    macro = N.macro_calendar(ctx)
    return {
        "mk": mk, "snaps": snaps, "by_t": by_t, "series": series, "breadth": br, "xu": xu,
        "xu30": next((x for x in mk["indices"] if x["code"] == "XU030"), {}),
        "intra": intra_sigs, "intra_status": intra_status, "weak": weak, "swing": swing, "fund": fund,
        "news": nw, "fx": fx, "macro": macro, "cfg_r": cfg_r, "need_intra": need_intra,
        "elapsed": round(time.time() - t0, 1),
    }


def data_quality(G: dict, slot: str) -> dict:
    details = []
    for ix in G["mk"]["indices"]:
        details.append({"name": f"{ix['name']} (günlük)", "quality": ix.get("quality", Q.UNAVAILABLE),
                        "note": ix.get("quality_note", ""), "last": ix.get("time")})
        if G["need_intra"]:
            details.append({"name": f"{ix['name']} (5 dk)", "quality": ix.get("intra_quality", Q.UNAVAILABLE),
                            "note": ix.get("intra_note", ""), "last": ix.get("intra_last_time")})
    snaps = G["snaps"]
    n = len(snaps)
    ok_d = sum(1 for s in snaps if Q.at_least(s.get("q_daily", Q.UNAVAILABLE), Q.INCOMPLETE))
    qd = Q.RELIABLE if ok_d >= 0.9 * n else (Q.INCOMPLETE if ok_d >= 0.5 * n else Q.UNAVAILABLE)
    details.append({"name": "Hisse günlük verileri", "quality": qd, "note": f"{ok_d}/{n} hissede kullanılabilir veri"})
    if G["need_intra"]:
        ok_i = sum(1 for s in snaps if Q.at_least(s.get("q_intra", Q.UNAVAILABLE), Q.DELAYED))
        qi = Q.DELAYED if ok_i >= 0.7 * n else (Q.INCOMPLETE if ok_i > 0 else Q.STALE)
        details.append({"name": "Hisse gün içi verileri", "quality": qi,
                        "note": f"{ok_i}/{n} hissede güncel (gecikmeli) 5 dk veri"})
    nw = G["news"]
    details.append({"name": "Haber / KAP başlıkları", "quality": Q.RELIABLE if nw["status"] == "çalışıyor" else Q.UNAVAILABLE,
                    "note": f"{len(nw['items'])} başlık; {nw['failed_queries']}/{nw['queries']} sorgu boş/başarısız"})
    fx = G["fx"]
    details.append({"name": "TCMB gösterge kurları", "quality": Q.UNAVAILABLE if fx.get("error") else Q.RELIABLE,
                    "note": fx.get("error") or f"Bülten tarihi {fx.get('date')}"})
    core = [d["quality"] for d in details[:2 if not G["need_intra"] else 4]]
    overall = Q.worst(*core, qd)
    return {"overall": overall, "label": Q.LABEL[overall], "details": details}


# ---------------------------------------------------------------------------
# Ortak bölümler
# ---------------------------------------------------------------------------

def index_table(G, intra: bool) -> dict:
    rows = []
    for ix in G["mk"]["indices"]:
        row = [ix["name"], fmt.num(ix.get("price")), B.chg(ix.get("chg"))]
        if intra:
            row += [B.chg(ix.get("since_open")), fmt.hm(_dt(ix.get("intra_last_time")))]
        else:
            row += [fmt.dmy_hm(_dt(ix.get("time")))]
        row.append(B.qcell(ix.get("intra_quality") if intra else ix.get("quality")))
        rows.append(row)
    cols = ["Endeks", "Son", "Günlük"] + (["Açılıştan beri", "Veri saati"] if intra else ["Veri zamanı"]) + ["Kalite"]
    return B.table(cols, rows, "veri")


def _dt(s):
    try:
        return dt.datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


def index_trend_text(ix: dict) -> dict | None:
    if ix.get("price") is None:
        return None
    parts = [f"{ix['name']}: eğilim {ix.get('trend')} — {ix.get('trend_explain', '')}"]
    if ix.get("rsi") is not None:
        rsi = ix["rsi"]
        tag = "aşırı alım bölgesinde" if rsi > 70 else ("aşırı satım bölgesinde" if rsi < 30 else "nötr bölgede")
        parts.append(f"RSI {fmt.num(rsi, 0)} ({tag}).")
    if ix.get("ema20"):
        parts.append(f"20 günlük ort. {fmt.num(ix['ema20'])}, 50 günlük {fmt.num(ix.get('ema50'))}, 200 günlük {fmt.num(ix.get('ema200'))}.")
    return B.text(" ".join(parts), "hesap")


def global_table(G) -> dict:
    rows = []
    for g in G["mk"]["global"]:
        rows.append([g["name"], fmt.num(g.get("price"), 4 if (g.get("price") or 0) < 10 else 2), B.chg(g.get("chg")),
                     fmt.dmy_hm(_dt(g.get("time"))), B.qcell(g.get("quality"))])
    return B.table(["Piyasa", "Son", "Değişim", "Veri zamanı", "Kalite"], rows, "veri",
                   "Yahoo Finance; vadeli ve Asya piyasaları gece de işlem görür, diğerleri son kapanıştır.")


def global_comment(G) -> dict:
    g = {x["code"]: x for x in G["mk"]["global"]}
    eq = [g[c]["chg"] for c in ("^GSPC", "^IXIC", "^GDAXI", "^N225", "ES=F") if c in g and g[c].get("chg") is not None]
    msgs = []
    if eq:
        up = sum(1 for x in eq if x > 0)
        if up >= len(eq) * 0.7:
            msgs.append("Küresel hisse piyasaları ağırlıklı olarak yükselişte: risk iştahı olumlu.")
        elif up <= len(eq) * 0.3:
            msgs.append("Küresel hisse piyasaları ağırlıklı olarak düşüşte: risk iştahı zayıf.")
        else:
            msgs.append("Küresel piyasalarda karışık bir görünüm var.")
    vix = g.get("^VIX", {}).get("price")
    if vix:
        if vix >= 25:
            msgs.append(f"VIX {fmt.num(vix, 1)}: küresel piyasalarda korku/oynaklık yüksek.")
        elif vix <= 15:
            msgs.append(f"VIX {fmt.num(vix, 1)}: küresel oynaklık düşük.")
    usd = g.get("USDTRY=X", {}).get("chg")
    if usd is not None and abs(usd) >= 0.8:
        msgs.append(f"Dolar/TL'de belirgin hareket ({fmt.pct(usd)}): kur oynaklığı bankalar ve ithalatçılar için önemli.")
    brent = g.get("BZ=F", {}).get("chg")
    if brent is not None and abs(brent) >= 2:
        msgs.append(f"Brent petrolde sert hareket ({fmt.pct(brent)}): havayolu, rafineri ve enerji hisselerini etkileyebilir.")
    return B.bullets(msgs, "yorum") if msgs else None


def fx_block(G) -> dict | None:
    fx = G["fx"]
    if fx.get("error") or not fx.get("rates"):
        return B.warn("TCMB gösterge kurları alınamadı.")
    rows = [[k, fmt.num(v, 4)] for k, v in fx["rates"].items()]
    return B.table(["Döviz", "TCMB döviz satış"], rows, "veri", f"TCMB bülten tarihi: {fx.get('date')} (günde bir kez ~15:30)")


def sector_table(G, n: int = 5) -> list[dict]:
    secs = [s for s in G["mk"]["sectors"] if s.get("chg") is not None]
    if not secs:
        return [B.warn("Sektör endeksi verisi alınamadı.")]
    top, bot = secs[:n], list(reversed(secs[-n:]))
    rows_t = [[s["name"], B.chg(s["chg"]), B.chg(s.get("ret20"))] for s in top]
    rows_b = [[s["name"], B.chg(s["chg"]), B.chg(s.get("ret20"))] for s in bot]
    return [B.table(["En güçlü sektörler", "Bugün", "20 gün"], rows_t, "veri"),
            B.table(["En zayıf sektörler", "Bugün", "20 gün"], rows_b, "veri")]


def movers_tables(G, n: int = 5) -> list[dict]:
    top, bot = S.movers(G["snaps"], n)
    def rows(lst):
        return [[B.tk(s["ticker"]), fmt.price(s.get("price")), B.chg(s.get("chg")),
                 fmt.num(s.get("relvol"), 1) + "x" if s.get("relvol") else "—"] for s in lst]
    if not top:
        return [B.warn("Hisse fiyat verisi alınamadı.")]
    return [B.table(["En çok yükselen", "Fiyat", "Değişim", "Hacim/ort."], rows(top), "veri",
                    "Düşük likiditeli hisseler hariç."),
            B.table(["En çok düşen", "Fiyat", "Değişim", "Hacim/ort."], rows(bot), "veri")]


def unusual_block(G) -> list[dict]:
    uv = S.unusual_volume(G["snaps"])
    out = []
    if uv:
        out.append(B.table(["Hisse", "Değişim", "Hacim/ort.", "Ölçüm"],
                           [[B.tk(s["ticker"]), B.chg(s.get("chg")), fmt.num(s["relvol"], 1) + "x", s.get("relvol_kind", "")]
                            for s in uv], "hesap",
                           "Hacim/ort.: bugünkü hacmin normal (ortalama) hacme oranı. 2x = normalin iki katı."))
    else:
        out.append(B.text("Belirgin olağandışı hacim tespit edilmedi.", "hesap"))
    moves = [s for s in G["snaps"] if s.get("unusual") and not any("hacim" in u for u in s["unusual"])]
    if moves:
        out.append(B.bullets([f"{s['ticker']}: {', '.join(s['unusual'])}" for s in moves[:8]], "hesap"))
    return out


def news_blocks(G, kap: bool) -> list[dict]:
    items = [n for n in G["news"]["items"] if bool(n.get("kap_related")) == kap]
    if G["news"]["status"] != "çalışıyor":
        return [B.warn("Haber kaynağına erişilemedi; bu bölüm boş.")]
    if not items:
        return [B.text("Bu dönemde dikkat çeken başlık bulunamadı.", "veri")]
    out = [B.news(items[:8])]
    if kap:
        out.append(B.text("Not: KAP otomatik erişime kapalı olduğu için başlıklar Google Haberler'den alınır. "
                          "Resmî metin için kap.org.tr'den doğrulayın.", "uyari"))
    return out


def sr_table(G, tickers: list[str]) -> dict:
    rows = []
    for ix in G["mk"]["indices"]:
        sr = ix.get("sr") or {}
        rows.append([ix["name"], fmt.num(ix.get("price")), " / ".join(fmt.num(x) for x in sr.get("supports", [])) or "—",
                     " / ".join(fmt.num(x) for x in sr.get("resistances", [])) or "—"])
    for t in tickers:
        s = G["by_t"].get(t)
        if not s or not s.get("sr"):
            continue
        rows.append([B.tk(t), fmt.price(s.get("price")), " / ".join(fmt.price(x) for x in s["sr"]["supports"]) or "—",
                     " / ".join(fmt.price(x) for x in s["sr"]["resistances"]) or "—"])
    return B.table(["", "Son", "Destekler", "Dirençler"], rows, "hesap",
                   "Destek: düşüşlerde alıcıların çıkabileceği seviye. Direnç: yükselişlerde satıcıların çıkabileceği seviye. "
                   "Geçmiş tepe/dipler ve pivot noktalarından hesaplanır.")


def swing_blocks(G, partial: bool) -> list[dict]:
    if not G["swing"]:
        return [B.text("Şu an kriterleri karşılayan swing kurulumu yok. Zorlama öneri üretilmedi.", "yorum")]
    out = [B.signals(G["swing"][:5])]
    if partial:
        out.append(B.text("Seans sürüyor: günlük mum kapanmadığı için swing seviyeleri kapanışta değişebilir.", "uyari"))
    return out


def intraday_blocks(G) -> list[dict]:
    st = G["intra_status"]
    analyzed = sum(1 for x in st.values() if x.get("analyzed"))
    out = []
    if analyzed == 0:
        reasons = {}
        for x in st.values():
            reasons[x.get("reason", "?")] = reasons.get(x.get("reason", "?"), 0) + 1
        top = max(reasons, key=reasons.get) if reasons else "veri yok"
        out.append(B.warn(f"Gün içi analiz yapılamadı: ücretsiz veride yeterli güncel 5 dakikalık mum yok ({top}). "
                          "Bayat veriyle sahte sinyal üretmemek için bu bölüm atlandı."))
        return out
    if G["intra"]:
        out.append(B.signals(G["intra"]))
    else:
        out.append(B.text(f"{analyzed} hisse tarandı; şu an kriterleri (risk/getiri ≥ "
                          f"{G.get('min_rr', 1.5)}) karşılayan gün içi kurulum yok. Zorlama öneri üretilmedi.", "yorum"))
    if G["weak"]:
        out.append(B.bullets([w["ticker"] + ": " + w["text"] for w in G["weak"][:5]], "yorum"))
    return out


def risks_list(G, ctx, slot: str) -> list[str]:
    out = []
    xu = G["xu"]
    g = {x["code"]: x for x in G["mk"]["global"]}
    vix = g.get("^VIX", {}).get("price")
    if vix and vix >= 25:
        out.append(f"Küresel oynaklık yüksek (VIX {fmt.num(vix, 1)}).")
    usd = g.get("USDTRY=X", {}).get("chg")
    if usd is not None and abs(usd) >= 0.8:
        out.append(f"Dolar/TL hareketli ({fmt.pct(usd)}).")
    for ev in G["macro"]:
        if ev["date"] == ctx.today.isoformat() and ev["time"]:
            out.append(f"Bugün saat {ev['time']}: {ev['event']}. Açıklama öncesi/sonrası sert hareket olabilir.")
        elif ev["date"] == ctx.cal.next_trading_day(ctx.today).isoformat() and ev["time"]:
            out.append(f"Yarın: {ev['event']}.")
    rsi = xu.get("rsi")
    if rsi and rsi > 72:
        out.append(f"BIST 100 RSI {fmt.num(rsi, 0)}: kısa vadede aşırı alım, kâr satışı riski.")
    if rsi and rsi < 30:
        out.append(f"BIST 100 RSI {fmt.num(rsi, 0)}: aşırı satım; tepki gelebilir ama düşüş eğilimi sürüyor olabilir.")
    if xu.get("ema200") and xu.get("price") and xu["price"] < xu["ema200"]:
        out.append("BIST 100, 200 günlük ortalamasının altında: uzun vadeli eğilim zayıf.")
    neg = [n for n in G["news"]["items"] if n["sentiment"] == "olumsuz"]
    if len(neg) >= 3:
        out.append(f"Son saatlerde {len(neg)} olumsuz tonlu başlık var; ilgili hisselerde dikkat.")
    st, note = ctx.cal.status(ctx.today)
    if st == "half":
        out.append(f"Bugün yarım gün seans ({note}); işlem süresi kısa, likidite düşük olabilir.")
    if G.get("dq", {}).get("overall") in (Q.STALE, Q.INCOMPLETE, Q.UNAVAILABLE):
        out.append("Veri kalitesi düşük: bu rapordaki yorumlara daha az güvenin.")
    if not out:
        out.append("Kural tabanlı kontrollerde öne çıkan ek bir risk görülmedi (bu, risk olmadığı anlamına gelmez).")
    return out


def watch_picks(G, n: int = 5) -> list[dict]:
    """Takip edilecek hisseler: swing adayları + olağandışı hareketler + izleme listesi."""
    picks, seen = [], set()
    for c in G["swing"]:
        if len(picks) >= n:
            break
        picks.append({"ticker": c["ticker"], "why": [f"{c['setup_tr']} (kalite {c['grade']})"] + c["reasons"][:2],
                      "kind": "hesap"})
        seen.add(c["ticker"])
    for s in sorted(G["snaps"], key=lambda s: -(s.get("relvol") or 0)):
        if len(picks) >= n:
            break
        if s["ticker"] in seen or not s.get("unusual") or s.get("liq") == "düşük":
            continue
        picks.append({"ticker": s["ticker"], "why": s["unusual"][:2], "kind": "veri"})
        seen.add(s["ticker"])
    return picks


def paper_block(ledger: dict, prices: dict) -> list[dict]:
    out = []
    rows = []
    for book, name in (("intraday", "Gün içi"), ("swing", "Swing")):
        st = P.stats(ledger, book)
        rows.append([name, fmt.tl(st["start_capital"]), fmt.tl(st["equity"]), str(st["trades"]),
                     fmt.pct(st["win_rate"], 0, sign=False) if st["win_rate"] is not None else "—",
                     fmt.num(st["avg_r"], 2) if st["avg_r"] is not None else "—", fmt.pct(st["max_drawdown_pct"], 1, sign=False),
                     str(st["open"])])
    out.append(B.table(["Defter", "Başlangıç", "Güncel", "İşlem", "Kazanma", "Ort. R", "Maks. düşüş", "Açık"], rows, "hesap",
                       "SİMÜLASYON: gerçek para yoktur. Komisyon ve kayma dahildir. R = kâr/zararın başlangıç riskine oranı."))
    opens = ledger.get("open", [])
    if opens:
        r_ = []
        for t in opens:
            px = prices.get(t["ticker"])
            pnl = (px - t["entry"]) / t["entry"] * 100 if px else None
            r_.append([B.tk(t["ticker"]), "Gün içi" if t["book"] == "intraday" else "Swing", fmt.price(t["entry"]),
                       fmt.price(px), B.chg(pnl), fmt.price(t["stop"]), fmt.price(t["t1"])])
        out.append(B.table(["Açık pozisyon", "Defter", "Giriş", "Son", "K/Z", "Stop", "Hedef 1"], r_, "hesap"))
    return out


# ---------------------------------------------------------------------------
# Rapor kurucular
# ---------------------------------------------------------------------------

def build_premarket(G, ctx) -> dict:
    xu, xu30 = G["xu"], G["xu30"]
    wl = ctx.cfg.watchlist
    secs = []
    secs.append(B.section("prev", "1. Önceki kapanış: BIST 100 ve BIST 30", [
        index_table(G, intra=False), index_trend_text(xu), index_trend_text(xu30),
        B.text("Bu rapor seans açılmadan önce hazırlanır; bugünün fiyatları henüz yoktur ve tahmin edilmez.", "uyari"),
    ]))
    secs.append(B.section("global", "2. Küresel piyasalar", [global_table(G), global_comment(G), fx_block(G)]))
    secs.append(B.section("news", "3. Gece gelen önemli haberler", news_blocks(G, kap=False)))
    secs.append(B.section("kap", "4. KAP açıklamalarıyla ilgili başlıklar", news_blocks(G, kap=True)))
    cal = G["macro"]
    secs.append(B.section("calendar", "5. Ekonomik takvim", [
        B.table(["Tarih", "Saat", "Olay", "Olası etki"],
                [[fmt.dmy(dt.date.fromisoformat(e["date"])), e["time"], e["event"], e["impact"]] for e in cal], "veri")
        if cal else B.text("Önümüzdeki 10 günde takvimde kayıtlı önemli bir makro veri yok.", "veri"),
    ]))
    picks = watch_picks(G)
    secs.append(B.section("watch", "6. Takip edilecek hisseler", [
        B.table(["Hisse", "Neden"], [[B.tk(p["ticker"]), "; ".join(p["why"])] for p in picks], "hesap")
        if picks else B.text("Belirgin bir aday çıkmadı.", "yorum"),
        _watchlist_table(G),
    ]))
    secs.append(B.section("levels", "7. Önemli destek ve direnç seviyeleri", [sr_table(G, wl)]))
    scen = []
    pv = xu.get("pivots") or {}
    if pv:
        scen.append(f"BIST 100 {fmt.num(pv['R1'])} üzerinde tutunursa {fmt.num(pv['R2'])} seviyesine doğru yükseliş senaryosu öne çıkar.")
        scen.append(f"{fmt.num(pv['S1'])} altına sarkarsa {fmt.num(pv['S2'])} test edilebilir.")
        scen.append(f"Pivot seviyesi {fmt.num(pv['P'])}: endeks bunun üzerinde kaldıkça gün içi görünüm görece olumlu sayılır.")
    for c in G["swing"][:3]:
        scen.append(f"{c['ticker']}: {fmt.price(c['entry_low'])}–{fmt.price(c['entry_high'])} bölgesi giriş bölgesi; "
                    f"{fmt.price(c['stop'])} altı senaryoyu bozar.")
    secs.append(B.section("scenarios", "8. Olası gün içi senaryolar", [B.bullets(scen, "senaryo") if scen else None]))
    secs.append(B.section("risks", "9. Seans riskleri", [B.bullets(risks_list(G, ctx, "premarket"), "yorum")]))
    head = (f"Açılış öncesi: BIST 100 önceki kapanış {fmt.num(xu.get('price'))} ({fmt.pct(xu.get('chg'))}). "
            f"Eğilim: {xu.get('trend', '—')}.")
    return {"sections": secs, "picks": {"title": "Bugün izlenecek en fazla 5 hisse", "items": picks}, "headline": head}


def _watchlist_table(G) -> dict | None:
    rows = []
    for t in G.get("wl", []):
        s = G["by_t"].get(t)
        if not s:
            continue
        rows.append([B.tk(t), fmt.price(s.get("price")), B.chg(s.get("chg")), s.get("trend", "—"),
                     fmt.num(s.get("rsi"), 0), B.qcell(s.get("q_daily"))])
    if not rows:
        return None
    return B.table(["İzleme listem", "Fiyat", "Değişim", "Eğilim", "RSI", "Kalite"], rows, "veri")


def build_opening(G, ctx) -> dict:
    xu = G["xu"]
    secs = []
    secs.append(B.section("indices", "1. BIST 100 ve BIST 30 hareketi", [index_table(G, intra=True)]))
    gap = xu.get("gap")
    txt = []
    if gap is not None:
        if gap > 0.5:
            txt.append(f"BIST 100 güne {fmt.pct(gap)} boşlukla yukarı başladı.")
        elif gap < -0.5:
            txt.append(f"BIST 100 güne {fmt.pct(gap)} boşlukla aşağı başladı.")
        else:
            txt.append(f"BIST 100 güne yatay başladı ({fmt.pct(gap)}).")
        so = xu.get("since_open")
        if so is not None:
            txt.append(f"Açılıştan bu yana {fmt.pct(so)}: " + ("alıcılar açılış seviyesini koruyor." if so >= 0 else "açılıştan sonra satış geldi."))
    bars = xu.get("bars_today") or 0
    txt.append(f"Ücretsiz veride şu ana kadar bugüne ait {bars} adet 5 dakikalık mum var "
               f"(son mum {fmt.hm(_dt(xu.get('intra_last_time')))}). İlk 15 dakikanın tamamı gözlemlenmemiş olabilir.")
    secs.append(B.section("open_action", "2. Açılış fiyat hareketi", [B.bullets(txt, "yorum")]))
    br = G["breadth"]
    secs.append(B.section("volume", "3. Hacim ve piyasa genişliği", [
        B.text(f"Taranan {br['total']} hissenin {br['adv']}'i yükselişte, {br['dec']}'i düşüşte.", "veri"),
        *unusual_block(G),
    ]))
    secs.append(B.section("movers", "4. En güçlü ve en zayıf hisseler", movers_tables(G)))
    secs.append(B.section("sectors", "5. Sektör hareketleri", sector_table(G)))
    secs.append(B.section("signals", "6. Gün içi teknik sinyaller ve olası fırsatlar", intraday_blocks(G)))
    pre = load_report(ctx.cfg.data_dir, ctx.today, "premarket")
    ch = []
    if pre:
        for p in (pre.get("picks") or {}).get("items", []):
            s = G["by_t"].get(p["ticker"])
            if s:
                ch.append(f"09:45'te izlenecek denen {p['ticker']}: şu an {fmt.price(s.get('price'))} ({fmt.pct(s.get('chg'))}).")
        ppv = None
        for sec in pre.get("sections", []):
            if sec["id"] == "scenarios":
                ppv = True
        if ppv and xu.get("pivots") and xu.get("price"):
            p = xu["pivots"]
            pos = "pivotun üzerinde" if xu["price"] > p["P"] else "pivotun altında"
            ch.append(f"BIST 100 şu an {pos} ({fmt.num(xu['price'])} / pivot {fmt.num(p['P'])}).")
    else:
        ch.append("09:45 raporu bulunamadı (üretilmemiş olabilir); karşılaştırma yapılamadı.")
    secs.append(B.section("changes", "7. 09:45 raporuna göre değişimler", [B.bullets(ch, "yorum")]))
    secs.append(B.section("risks", "8. Riskler", [B.bullets(risks_list(G, ctx, "opening"), "yorum")]))
    head = (f"Açılış sonrası: BIST 100 {fmt.num(xu.get('price'))} ({fmt.pct(xu.get('chg'))}), "
            f"{br['adv']} yükselen / {br['dec']} düşen.")
    picks = [{"ticker": s["ticker"], "why": [s["strategy_tr"], f"Risk/getiri {fmt.num(s['rr'], 1)}"] + s["reasons"][:1],
              "kind": "hesap"} for s in G["intra"][:5]]
    return {"sections": secs, "picks": {"title": "Gün içi izlenecek adaylar", "items": picks}, "headline": head}


def invalidated(G, ctx) -> list[str]:
    out = []
    op = load_report(ctx.cfg.data_dir, ctx.today, "opening")
    sigs = []
    if op:
        for sec in op.get("sections", []):
            for it in sec.get("items", []):
                if it.get("type") == "signals":
                    sigs += it["signals"]
    for sg in sigs:
        s = G["by_t"].get(sg["ticker"])
        if not s or s.get("price") is None:
            continue
        if s["price"] <= sg["stop"]:
            out.append(f"{sg['ticker']} ({sg.get('strategy_tr') or sg.get('setup_tr')}): fiyat {fmt.price(s['price'])}, stop "
                       f"{fmt.price(sg['stop'])} altına indi → geçersiz.")
        elif s["price"] >= sg["t1"]:
            out.append(f"{sg['ticker']}: hedef 1 ({fmt.price(sg['t1'])}) görüldü.")
    prev_close = load_report(ctx.cfg.data_dir, ctx.cal.previous_trading_day(ctx.today), "close")
    if prev_close:
        for sec in prev_close.get("sections", []):
            for it in sec.get("items", []):
                if it.get("type") == "signals":
                    for sg in it["signals"]:
                        s = G["by_t"].get(sg["ticker"])
                        if s and s.get("price") is not None and s["price"] <= sg["stop"]:
                            out.append(f"{sg['ticker']} (dünkü swing adayı): stop {fmt.price(sg['stop'])} altında → kurulum bozuldu.")
    return out


def build_midday(G, ctx, ledger) -> dict:
    xu = G["xu"]
    br = G["breadth"]
    secs = []
    direction, why = M.market_direction(xu, br)
    secs.append(B.section("direction", "1. Mevcut piyasa yönü", [index_table(G, intra=True), B.text(f"Yön: {direction}. {why}", "yorum")]))
    op = load_report(ctx.cfg.data_dir, ctx.today, "opening")
    ch = []
    if xu.get("since_open") is not None:
        ch.append(f"BIST 100 açılıştan bu yana {fmt.pct(xu['since_open'])}.")
    if op:
        prev_head = op.get("headline")
        if prev_head:
            ch.append(f"10:15 raporundaki durum: {prev_head}")
    secs.append(B.section("since_open", "2. Açılıştan bu yana değişim", [B.bullets(ch, "veri")]))
    secs.append(B.section("intraday", "3. Gün içi fırsatlar", intraday_blocks(G)))
    secs.append(B.section("swing", "4. Swing fırsatları", swing_blocks(G, partial=True)))
    rot = []
    if op:
        prev_rank = {}
        for sec in op.get("sections", []):
            if sec["id"] == "sectors":
                for it in sec["items"]:
                    if it.get("type") == "table":
                        for i, row in enumerate(it["rows"]):
                            prev_rank[row[0]] = (it["columns"][0], i)
        secs_now = [s for s in G["mk"]["sectors"] if s.get("chg") is not None]
        for s in secs_now[:3]:
            if prev_rank.get(s["name"], ("",))[0].startswith("En zayıf"):
                rot.append(f"{s['name']}: sabah en zayıflar arasındaydı, şimdi en güçlüler arasında ({fmt.pct(s['chg'])}).")
        for s in secs_now[-3:]:
            if prev_rank.get(s["name"], ("",))[0].startswith("En güçlü"):
                rot.append(f"{s['name']}: sabah en güçlüler arasındaydı, şimdi en zayıflar arasında ({fmt.pct(s['chg'])}).")
    if not rot:
        rot.append("Sabaha göre belirgin bir sektör rotasyonu yok.")
    secs.append(B.section("rotation", "5. Sektör rotasyonu", [*sector_table(G, 4), B.bullets(rot, "yorum")]))
    secs.append(B.section("unusual", "6. Olağandışı hareketler", [*movers_tables(G, 4), *unusual_block(G)]))
    secs.append(B.section("news", "7. Önemli haberler ve KAP başlıkları", news_blocks(G, kap=True) + news_blocks(G, kap=False)[:1]))
    inv = invalidated(G, ctx)
    secs.append(B.section("invalid", "8. Geçersiz kalan / hedefe ulaşan sinyaller",
                          [B.bullets(inv, "hesap") if inv else B.text("Sabahki sinyallerden geçersiz kalan yok.", "hesap")]))
    secs.append(B.section("risks", "9. Risk uyarıları", [B.bullets(risks_list(G, ctx, "midday"), "yorum")]))
    prices = {s["ticker"]: s.get("price") for s in G["snaps"] if s.get("price")}
    secs.append(B.section("paper", "10. Simülasyon portföyü durumu", paper_block(ledger, prices)))
    picks = [{"ticker": s["ticker"], "why": ["Gün içi: " + s["strategy_tr"]] + s["reasons"][:1], "kind": "hesap"} for s in G["intra"][:3]]
    picks += [{"ticker": c["ticker"], "why": ["Swing: " + c["setup_tr"] + f" ({c['grade']})"] + c["reasons"][:1], "kind": "hesap"}
              for c in G["swing"][:3]]
    head = f"Gün ortası: BIST 100 {fmt.num(xu.get('price'))} ({fmt.pct(xu.get('chg'))}), yön: {direction}."
    return {"sections": secs, "picks": {"title": "En fazla 3 gün içi + 3 swing adayı", "items": picks}, "headline": head}


def signal_performance(G, ctx) -> list[list]:
    rows = []
    for slot in ("opening", "midday"):
        rep = load_report(ctx.cfg.data_dir, ctx.today, slot)
        if not rep:
            continue
        for sec in rep.get("sections", []):
            for it in sec.get("items", []):
                if it.get("type") != "signals":
                    continue
                for sg in it["signals"]:
                    if sg.get("kind") != "intraday":
                        continue
                    ser = G["series"].get(sg["ticker"], {}).get("intra")
                    ev = I.evaluate_signal(sg, ser, dt.datetime.fromisoformat(sg["time"]))
                    rows.append([B.tk(sg["ticker"]), SLOTS[slot]["short"], sg["strategy_tr"], fmt.price(sg["entry"]),
                                 ev["result"], B.chg(ev.get("pct"))])
    return rows


def build_close(G, ctx, ledger, closed_today: list, opened_swing: list, fund_changes: list) -> dict:
    xu, xu30 = G["xu"], G["xu30"]
    br = G["breadth"]
    secs = []
    secs.append(B.section("indices", "1–2. BIST 100 ve BIST 30 kapanış", [
        index_table(G, intra=False), index_trend_text(xu), index_trend_text(xu30)]))
    secs.append(B.section("sectors", "3. En güçlü ve en zayıf sektörler", sector_table(G)))
    secs.append(B.section("movers", "4. Önemli hisse hareketleri", movers_tables(G)))
    tl_today = sum(s.get("tl_vol_today") or 0 for s in G["snaps"])
    tl_avg = sum(s.get("avg_tl_vol20") or 0 for s in G["snaps"])
    vol_items = []
    if tl_today and tl_avg:
        ratio = tl_today / tl_avg
        vol_items.append(B.text(f"Taranan hisselerde toplam işlem hacmi {fmt.tl(tl_today)}; 20 günlük ortalamanın "
                                f"{fmt.num(ratio, 2)} katı. " + ("Hacim ortalamanın üzerinde: hareketin arkasında katılım var."
                                                                 if ratio > 1.15 else ("Hacim zayıf: hareketin gücü sorgulanabilir."
                                                                                       if ratio < 0.85 else "Hacim normal seviyede.")), "hesap"))
    vol_items += unusual_block(G)
    secs.append(B.section("volume", "5. Hacim analizi", vol_items))
    secs.append(B.section("kap", "6. KAP açıklamalarıyla ilgili başlıklar", news_blocks(G, kap=True)))
    perf = signal_performance(G, ctx)
    secs.append(B.section("perf", "7. Gün içi sinyal performansı", [
        B.table(["Hisse", "Rapor", "Strateji", "Giriş", "Sonuç", "Getiri"], perf, "hesap",
                "Sinyal anındaki gecikmeli fiyattan giriş varsayılır; aynı mumda stop ve hedef görülürse stop sayılır.")
        if perf else B.text("Bugün değerlendirilecek gün içi sinyal yoktu.", "hesap")]))
    pitems = paper_block(ledger, {s["ticker"]: s.get("price") for s in G["snaps"] if s.get("price")})
    if closed_today:
        pitems.append(B.table(["Bugün kapanan", "Defter", "K/Z (TL)", "R", "Neden"],
                              [[B.tk(t["ticker"]), t["book"], fmt.num(t["pnl"], 0), fmt.num(t.get("r_multiple"), 2), t["exit_reason"]]
                               for t in closed_today], "hesap"))
    if opened_swing:
        pitems.append(B.text("Yeni swing simülasyon pozisyonu: " + ", ".join(t["ticker"] for t in opened_swing), "hesap"))
    secs.append(B.section("paper", "8. Simülasyon (kağıt üzerinde) işlem sonuçları", pitems))
    secs.append(B.section("swing", "9. Güncel swing adayları", swing_blocks(G, partial=False)))
    lt = []
    if fund_changes:
        lt.append(B.table(["Hisse", "Önceki", "Yeni"], [[B.tk(t), a, b] for t, a, b in fund_changes], "yorum"))
    good = [m for m in G["fund"] if m["class"] == "Güçlü şirket, makul değerleme"]
    if good:
        lt.append(B.table(["Güçlü + makul değerleme", "Sektör", "F/K", "PD/DD", "ROE"],
                          [[B.tk(m["ticker"]), m["sector"], fmt.num(m.get("pe"), 1), fmt.num(m.get("pb"), 2),
                            fmt.pct(m.get("roe"), 0, sign=False) if m.get("roe") is not None else "—"] for m in good[:8]], "yorum"))
    if not lt:
        lt.append(B.text("Uzun vade sınıflandırmasında değişiklik yok." if G["fund"] else
                         "Temel analiz verisi henüz toplanıyor (her gün bir kısmı güncellenir).", "yorum"))
    lt.append(B.text(F.INFLATION_NOTE, "uyari"))
    secs.append(B.section("longterm", "10. Uzun vade izleme listesi değişiklikleri", lt))
    # Yarın
    direction, why = M.market_direction(xu, br)
    outlook = [f"Bugünün yönü: {direction}. {why}"]
    if xu.get("trend"):
        outlook.append(f"Teknik eğilim: {xu['trend']}. {xu.get('trend_explain', '')}")
    pv = xu.get("pivots") or {}
    if pv:
        outlook.append(f"Yarın için pivot {fmt.num(pv['P'])}; üzerinde {fmt.num(pv['R1'])}, altında {fmt.num(pv['S1'])} izlenebilir.")
    nxt = ctx.cal.next_trading_day(ctx.today)
    for ev in G["macro"]:
        if ev["date"] == nxt.isoformat():
            outlook.append(f"Yarın {ev['time']}: {ev['event']}.")
    picks = watch_picks(G)
    secs.append(B.section("tomorrow", f"Yarın ({fmt.gun_adi(nxt)}, {fmt.dmy(nxt)}) için görünüm", [
        B.bullets(outlook, "senaryo"), sr_table(G, ctx.cfg.watchlist),
        B.table(["Yarın izlenecek", "Neden"], [[B.tk(p["ticker"]), "; ".join(p["why"])] for p in picks], "hesap") if picks else None,
    ]))
    imp = [f"{n['title']} ({n['source']})" for n in G["news"]["items"] if n.get("tickers") or n["category"] != "Genel"][:4]
    summary = [f"BIST 100 {fmt.num(xu.get('price'))} ({fmt.pct(xu.get('chg'))}), BIST 30 {fmt.num(xu30.get('price'))} ({fmt.pct(xu30.get('chg'))}).",
               f"{br['adv']} hisse yükseldi, {br['dec']} hisse düştü."]
    top, bot = S.movers(G["snaps"], 1)
    if top:
        summary.append(f"Günün öne çıkanı {top[0]['ticker']} ({fmt.pct(top[0]['chg'])}), en zayıfı {bot[0]['ticker']} ({fmt.pct(bot[0]['chg'])}).")
    head = f"Kapanış: BIST 100 {fmt.num(xu.get('price'))} ({fmt.pct(xu.get('chg'))}), {br['adv']} yükselen / {br['dec']} düşen."
    return {"sections": secs, "picks": {"title": "Yarın izlenecek hisseler", "items": picks}, "headline": head,
            "summary": summary, "important": imp}


# ---------------------------------------------------------------------------
# Ana akış
# ---------------------------------------------------------------------------

def generate(ctx, slot: str, refresh_fund: str | None = None) -> dict:
    data_dir = ctx.cfg.data_dir
    G = gather(ctx, slot, refresh_fund)
    G["wl"] = ctx.cfg.watchlist
    G["min_rr"] = ctx.cfg.get("intraday", "min_rr", default=1.5)
    dq = data_quality(G, slot)
    G["dq"] = dq
    xu = G["xu"]
    warnings = []
    status = "ok"
    # Veri yoksa uydurma rapor yerine uyarı raporu
    if xu.get("price") is None:
        status = "partial"
        warnings.append("BIST 100 verisi alınamadı. Ücretsiz veri kaynağı geçici olarak erişilemez olabilir. "
                        "Bu raporda piyasa yorumu yapılmadı; bir sonraki raporu bekleyin veya elle yeniden üretin.")
    if slot != "premarket" and xu.get("last_close_date") is not None:
        daily_last = None
        s = G["mk"]["_series"]["idx_d"].get("XU100")
        if s is not None and s.ok:
            daily_last = s.dates()[-1]
        if (daily_last is not None and daily_last < ctx.today
                and ctx.now > ctx.cal.session(ctx.today)[0] + dt.timedelta(minutes=45)):
            status = "partial"
            warnings.append(f"Bugüne ait BIST 100 verisi yok (son veri {fmt.dmy(daily_last)}). Piyasa bugün kapalı olabilir "
                            "(takvimde olmayan bir tatil) ya da veri kaynağı gecikiyor. Bu nedenle bugünün fiyatları yorumlanmadı.")
    ledger_path = data_dir / "paper" / "ledger.json"
    ledger = P.load(ledger_path, ctx.cfg.settings)
    cfg_r = G["cfg_r"]
    prices = {s["ticker"]: s["price"] for s in G["snaps"] if s.get("price")}
    closed_today, opened_swing, fund_changes = [], [], []
    paper_on = status == "ok"
    if paper_on and slot in ("opening", "midday", "close"):
        bars = {}
        for t in {x["ticker"] for x in ledger["open"] if x["book"] == "intraday"}:
            ser = G["series"].get(t, {}).get("intra")
            if ser is not None and ser.ok:
                bars[t] = P.bars_from_series(ser.only_date(ctx.today))
        closed_today += P.update_book(ledger, "intraday", bars, cfg_r, ctx.now, force_close=(slot == "close"),
                                      last_prices=prices)
        if slot in ("opening", "midday") and ctx.cfg.get("intraday", "auto_paper", default=True):
            for sg in G["intra"][:2]:
                if sg.get("liq") == "düşük" or sg.get("confidence") == "düşük":
                    continue
                P.open_trade(ledger, "intraday", sg, dt.datetime.fromisoformat(sg["time"]), cfg_r, max_open=3,
                             max_per_day=int(ctx.cfg.get("intraday", "max_paper_per_day", default=2)))
    if paper_on and slot == "close":
        dbars = {}
        for t in {x["ticker"] for x in ledger["open"] if x["book"] == "swing"}:
            ser = G["series"].get(t, {}).get("daily")
            if ser is not None and ser.ok:
                dbars[t] = P.bars_from_series(ser)
        closed_today += P.update_book(ledger, "swing", dbars, cfg_r, ctx.now,
                                      max_hold_days=int(ctx.cfg.get("swing", "max_hold_days", default=20)), last_prices=prices)
        if ctx.cfg.get("swing", "auto_paper", default=True):
            for c in G["swing"][:2]:
                if c["grade"] == "C":
                    continue
                t, _ = P.open_trade(ledger, "swing", c, ctx.now, cfg_r,
                                    max_open=int(ctx.cfg.get("swing", "max_open", default=5)), max_per_day=1)
                if t:
                    opened_swing.append(t)
        for book in ("intraday", "swing"):
            P.mark_equity(ledger, book, ctx.today, prices)
        prev_f = load_json(data_dir / "latest" / "fundamentals.json", {}) or {}
        prev_cls = {m["ticker"]: m["class"] for m in prev_f.get("items", [])}
        for m in G["fund"]:
            a = prev_cls.get(m["ticker"])
            if a and a != m["class"]:
                fund_changes.append((m["ticker"], a, m["class"]))
    if slot == "premarket":
        body = build_premarket(G, ctx)
    elif slot == "opening":
        body = build_opening(G, ctx)
    elif slot == "midday":
        body = build_midday(G, ctx, ledger)
    else:
        body = build_close(G, ctx, ledger, closed_today, opened_swing, fund_changes)
    if status != "ok":
        body["sections"] = [B.section("warning", "Uyarı: veri sorunu", [B.warn(w) for w in warnings])] + [
            sec for sec in body["sections"] if sec["id"] in ("global", "news", "kap", "calendar")]
        body["picks"] = {"title": body["picks"]["title"], "items": []}
    sched = slot_time(ctx.today, slot)
    delay = round((ctx.now - sched).total_seconds() / 60)
    report = {
        "id": f"{ctx.today.isoformat()}_{slot}", "slot": slot, "title": SLOTS[slot]["title"],
        "date": ctx.today.isoformat(), "day_name": fmt.gun_adi(ctx.today), "scheduled_for": SLOTS[slot]["short"],
        "generated_at": ctx.now.isoformat(timespec="seconds"), "delay_minutes": delay,
        "on_time": -5 <= delay <= 10, "trigger": ctx.trigger, "status": status, "warnings": warnings,
        "headline": body.get("headline", ""), "summary": body.get("summary", []), "important": body.get("important", []),
        "data_quality": dq, "sections": body["sections"], "picks": body["picks"],
        "sources": [
            yahoo.SOURCE_NAME + " — endeks, sektör, hisse ve küresel piyasa fiyatları",
            "TCMB gösterge kurları (tcmb.gov.tr/kurlar, resmî, ücretsiz)",
            G["news"]["source"],
            "Makro takvim ve enflasyon: config/macro.json (elle güncellenir)",
        ],
        "kinds": B.KINDS, "disclaimer": DISCLAIMER, "elapsed_sec": G["elapsed"],
        "universe_note": f"Taranan evren: {len(G['snaps'])} hisse (yaklaşık BIST 100 takip listesi + izleme listeniz). "
                         "Resmî endeks üyelik listesi değildir.",
    }
    save_json(report_path(data_dir, ctx.today, slot), report, compact=True)
    if status == "ok" or slot == "premarket":
        P.save(ledger_path, ledger)
    write_latest(ctx, G, ledger, report)
    return report


def write_latest(ctx, G, ledger, report):
    d = ctx.cfg.data_dir / "latest"
    swing_by = {c["ticker"]: c for c in G["swing"]}
    intra_by = {}
    for s in G["intra"]:
        intra_by.setdefault(s["ticker"], s)
    fund_by = {m["ticker"]: m for m in G["fund"]}
    stocks = []
    for s in G["snaps"]:
        t = s["ticker"]
        ser = G["series"].get(t, {}).get("daily")
        spark = [r(x) for x in ser.c[-90:]] if ser is not None and ser.ok else []
        item = {k: v for k, v in s.items() if not k.startswith("_")}
        item["spark"] = spark
        item["swing"] = swing_by.get(t)
        item["intraday"] = intra_by.get(t)
        item["intra_status"] = G["intra_status"].get(t)
        f = fund_by.get(t)
        item["fund_class"] = f["class"] if f else None
        stocks.append(item)
    save_json(d / "stocks.json", {"generated_at": report["generated_at"], "report_id": report["id"],
                                  "items": stocks}, compact=True)
    if G["fund"]:
        save_json(d / "fundamentals.json", {"generated_at": report["generated_at"], "note": F.INFLATION_NOTE,
                                            "items": G["fund"]}, compact=True)
    mk = {k: v for k, v in G["mk"].items() if not k.startswith("_")}
    save_json(d / "market.json", {"generated_at": report["generated_at"], **mk, "breadth": G["breadth"],
                                  "news": G["news"], "macro": G["macro"], "fx": G["fx"]}, compact=True)
    save_json(d / "paper.json", {"generated_at": report["generated_at"],
                                 "stats": [P.stats(ledger, b) for b in ("intraday", "swing")],
                                 "open": ledger["open"], "closed": ledger["closed"][-50:],
                                 "equity": ledger["equity"], "note": ledger.get("note")}, compact=True)
