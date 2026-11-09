"""Uzun vadeli temel analiz.

Kaynak: Yahoo Finance yıllık mali tablo zaman serileri (ücretsiz). Kısıtlar:
  * BIST şirketleri için veri eksik olabilir; para birimi etiketleri tutarsız olabilir.
  * Türkiye'de 2023'ten itibaren enflasyon muhasebesi (TMS 29) uygulanıyor. Nominal
    büyüme yanıltıcıdır; TL raporlayan şirketlerde büyümeyi yıllık TÜFE ile
    reelleştiriyoruz (yaklaşık).
  * Değerleme yalnızca AYNI SEKTÖRDEKİ şirketlerle kıyaslanır (en az 3 benzer gerekir).
  * Düşük F/K tek başına "ucuz" demek değildir.
"""
from __future__ import annotations

from . import fmt
import statistics
import time

from . import yahoo
from .util import load_json, parallel_map, r, save_json

FINANCIAL_SECTORS = {"Bankacılık", "Sigorta", "Aracı Kurum", "Holding"}
TAX = 0.25

CLASS_EXPLAIN = {
    "Güçlü şirket, makul değerleme": "Kârlılık, borçluluk ve nakit üretimi iyi; sektör benzerlerine göre pahalı görünmüyor. Uzun vadeli izleme listesi için ilk bakılacak grup.",
    "Güçlü şirket ama pahalı": "İşletme kalitesi iyi ama piyasa bunu fiyata büyük ölçüde yansıtmış. Daha uygun fiyat için sabır gerekebilir.",
    "Ucuz ama riskli": "Çarpanlar sektöre göre düşük ama kârlılık, borç ya da nakit akışında zayıflık var. Ucuzluğun bir nedeni olabilir.",
    "Temelleri zayıflıyor": "Kâr düşüyor, zarar var ya da marjlar belirgin geriliyor. Toparlanma işaretleri görülene kadar temkin.",
    "İzlemeye değer": "Belirgin bir güçlü/zayıf tablo yok ya da sektör karşılaştırması yapılamadı. Gelişmeleri izlemek mantıklı.",
    "Veri yetersiz": "Ücretsiz kaynakta yeterli mali tablo verisi yok. Şirketin KAP'taki finansal raporlarına bakılmalı.",
}

INFLATION_NOTE = ("Türkiye'de 2023'ten itibaren enflasyon muhasebesi (TMS 29) uygulanıyor. Ücretsiz kaynaktaki yıllık "
                  "rakamlar farklı tarihlerin satın alma gücüyle raporlanmış olabilir. TL raporlayan şirketlerde büyümeyi "
                  "yıllık TÜFE ile reel hale getirdik; sonuçlar yaklaşıktır. Kesin karar için KAP'taki resmi raporlara bakın.")


def _series(ts: dict, key: str) -> list[dict]:
    return (ts.get("annual") or {}).get(key) or []


def _val(rows: list[dict], i: int = -1):
    try:
        return rows[i]["value"]
    except (IndexError, KeyError, TypeError):
        return None


def _year(rows: list[dict], i: int = -1):
    try:
        return rows[i]["date"][:4]
    except (IndexError, KeyError, TypeError):
        return None


def real_growth(nominal_pct: float | None, cpi_pct: float | None) -> float | None:
    if nominal_pct is None or cpi_pct is None:
        return None
    return ((1 + nominal_pct / 100) / (1 + cpi_pct / 100) - 1) * 100


def growth(rows: list[dict]) -> float | None:
    a, b = _val(rows, -1), _val(rows, -2)
    if a is None or b is None or b <= 0:
        return None
    return (a / b - 1) * 100


def metrics(ticker: str, ts: dict, dividends: list, price: float | None, sector: str, usd: bool,
            cpi: dict) -> dict:
    rev, ebitda, ni = _series(ts, "TotalRevenue"), _series(ts, "EBITDA"), _series(ts, "NetIncome")
    fcf, debt, cash = _series(ts, "FreeCashFlow"), _series(ts, "TotalDebt"), _series(ts, "CashAndCashEquivalents")
    eq, ebit, ic = _series(ts, "StockholdersEquity"), _series(ts, "EBIT"), _series(ts, "InvestedCapital")
    tr = ts.get("trailing") or {}
    fin = sector in FINANCIAL_SECTORS
    m: dict = {"ticker": ticker, "sector": sector, "financial": fin, "reporting": "USD" if usd else "TL",
               "year": _year(ni) or _year(rev), "notes": []}
    ccys = {row.get("ccy") for row in (rev or ni)[-3:] if row.get("ccy")}
    if len(ccys) > 1 and not usd:
        m["notes"].append("Kaynakta para birimi etiketleri tutarsız; büyüme oranlarını dikkatle yorumlayın")
    year = m["year"]
    cpi_y = cpi.get(year) if (year and not usd) else None
    if year and not usd and cpi_y is None:
        m["notes"].append(f"{year} yılı TÜFE değeri ayarlarda yok; reel büyüme hesaplanmadı")
    m["revenue"] = _val(rev)
    m["net_income"] = _val(ni)
    m["ebitda"] = _val(ebitda)
    m["fcf"] = _val(fcf)
    m["fcf_prev"] = _val(fcf, -2)
    m["net_margin"] = r(m["net_income"] / m["revenue"] * 100) if (m["net_income"] is not None and m["revenue"]) else None
    pm = (_val(ni, -2) / _val(rev, -2) * 100) if (_val(ni, -2) is not None and _val(rev, -2)) else None
    m["net_margin_prev"] = r(pm)
    m["ebitda_margin"] = r(m["ebitda"] / m["revenue"] * 100) if (m["ebitda"] and m["revenue"]) else None
    e1, e0 = _val(eq, -1), _val(eq, -2)
    if m["net_income"] is not None and e1:
        avg_eq = (e1 + e0) / 2 if e0 else e1
        m["roe"] = r(m["net_income"] / avg_eq * 100) if avg_eq > 0 else None
    else:
        m["roe"] = None
    eb, icv = _val(ebit), _val(ic)
    m["roic"] = r(eb * (1 - TAX) / icv * 100) if (eb is not None and icv and icv > 0) else None
    d, c = _val(debt), _val(cash)
    m["net_debt"] = (d - c) if (d is not None and c is not None) else None
    m["nd_ebitda"] = r(m["net_debt"] / m["ebitda"], 2) if (m["net_debt"] is not None and m["ebitda"] and m["ebitda"] > 0) else None
    m["rev_growth"] = r(growth(rev))
    m["ni_growth"] = r(growth(ni))
    m["eq_growth"] = r(growth(eq))
    m["rev_growth_real"] = r(real_growth(m["rev_growth"], cpi_y)) if not usd else m["rev_growth"]
    m["ni_growth_real"] = r(real_growth(m["ni_growth"], cpi_y)) if not usd else m["ni_growth"]
    m["eq_growth_real"] = r(real_growth(m["eq_growth"], cpi_y)) if not usd else m["eq_growth"]
    m["roe_real"] = r(m["roe"] - cpi_y) if (m["roe"] is not None and cpi_y is not None) else (m["roe"] if usd else None)
    ni_vals = [x["value"] for x in ni[-3:]]
    m["ni_down_2y"] = len(ni_vals) == 3 and ni_vals[2] < ni_vals[1] < ni_vals[0]

    def trailing(key):
        row = tr.get(key)
        if not row:
            return None, None
        return row.get("value"), row.get("date")

    pe, pe_d = trailing("PeRatio")
    pb, pb_d = trailing("PbRatio")
    ev, ev_d = trailing("EnterprisesValueEBITDARatio")
    mc, _ = trailing("MarketCap")
    m["pe"] = r(pe) if (pe and pe > 0) else None
    m["pb"] = r(pb) if (pb and pb > 0) else None
    m["ev_ebitda"] = r(ev) if (ev and ev > 0 and not fin) else None
    m["market_cap"] = mc
    m["valuation_date"] = pe_d or pb_d or ev_d
    # Temettü: son 5 yılda kaç yıl dağıttı, son 12 ay verimi
    now = time.time()
    years = sorted({time.gmtime(t).tm_year for t, a in dividends if a > 0 and t > now - 5.2 * 365 * 86400})
    last12 = sum(a for t, a in dividends if t > now - 365 * 86400)
    m["div_years_5y"] = len(years)
    m["div_yield"] = r(last12 / price * 100) if (price and last12) else (0.0 if price else None)
    return m


def quality_score(m: dict) -> tuple[float | None, list[str], list[str]]:
    pos, neg = [], []
    pts, maxp = 0.0, 0
    fin = m["financial"]

    def check(cond, good, bad):
        nonlocal pts, maxp
        if cond is None:
            return
        maxp += 1
        if cond:
            pts += 1
            pos.append(good)
        else:
            neg.append(bad)

    ni = m.get("net_income")
    check(None if ni is None else ni > 0, "Kâr ediyor", "Zarar açıklamış")
    rr_ = m.get("roe_real")
    check(None if rr_ is None else rr_ > 0,
          f"Özsermaye kârlılığı (ROE %{fmt.num(m['roe'], 0)}) enflasyonun üzerinde" if m.get("roe") is not None else "ROE iyi",
          f"Özsermaye kârlılığı (ROE %{fmt.num(m['roe'], 0)}) enflasyonun altında" if m.get("roe") is not None else "ROE zayıf")
    if fin:
        g = m.get("eq_growth_real")
        check(None if g is None else g > 0, "Özsermaye reel olarak büyüyor", "Özsermaye reel olarak küçülüyor")
        g2 = m.get("ni_growth_real")
        check(None if g2 is None else g2 > 0, "Net kâr reel olarak arttı", "Net kâr reel olarak geriledi")
    else:
        nd = m.get("nd_ebitda")
        if m.get("net_debt") is not None and m["net_debt"] < 0:
            check(True, "Net nakit pozisyonunda (borcundan fazla nakdi var)", "")
        else:
            check(None if nd is None else nd < 2, f"Borç yükü makul (Net borç/FAVÖK {nd})" if nd is not None else "",
                  f"Borç yükü yüksek (Net borç/FAVÖK {nd})" if nd is not None else "")
        f = m.get("fcf")
        check(None if f is None else f > 0, "Serbest nakit akışı pozitif", "Serbest nakit akışı negatif")
        g = m.get("rev_growth_real")
        check(None if g is None else g > 0, f"Satışlar reel olarak büyüdü ({fmt.pct(g, 0)})" if g is not None else "",
              f"Satışlar reel olarak küçüldü ({fmt.pct(g, 0)})" if g is not None else "")
    if maxp < 3:
        return None, pos, neg
    return pts / maxp, pos, neg


def classify_all(metrics_list: list[dict]) -> list[dict]:
    by_sector: dict[str, list[dict]] = {}
    for m in metrics_list:
        by_sector.setdefault(m["sector"], []).append(m)
    med = {}
    for sec, ms in by_sector.items():
        pes = [x["pe"] for x in ms if x.get("pe")]
        pbs = [x["pb"] for x in ms if x.get("pb")]
        med[sec] = {
            "pe": statistics.median(pes) if len(pes) >= 3 else None,
            "pb": statistics.median(pbs) if len(pbs) >= 3 else None,
            "n": len(ms),
        }
    out = []
    for m in metrics_list:
        q, pos, neg = quality_score(m)
        sm = med.get(m["sector"], {})
        rels = []
        if m.get("pe") and sm.get("pe"):
            rels.append(m["pe"] / sm["pe"])
        if m.get("pb") and sm.get("pb"):
            rels.append(m["pb"] / sm["pb"])
        rel = sum(rels) / len(rels) if rels else None
        deteriorating = (m.get("net_income") is not None and m["net_income"] < 0) or m.get("ni_down_2y") or (
            m.get("net_margin") is not None and m.get("net_margin_prev") and m["net_margin_prev"] > 0
            and m["net_margin"] < m["net_margin_prev"] * 0.6)
        if q is None:
            cls = "Veri yetersiz"
        elif deteriorating:
            cls = "Temelleri zayıflıyor"
        elif rel is None:
            cls = "İzlemeye değer"
            m["notes"].append("Aynı sektörde yeterli benzer şirket verisi olmadığından değerleme kıyaslanmadı")
        elif q >= 0.6 and rel <= 1.1:
            cls = "Güçlü şirket, makul değerleme"
        elif q >= 0.6:
            cls = "Güçlü şirket ama pahalı"
        elif rel <= 0.85:
            cls = "Ucuz ama riskli"
        else:
            cls = "İzlemeye değer"
        if m.get("pe") and m["pe"] < 5 and cls in ("Ucuz ama riskli", "İzlemeye değer"):
            m["notes"].append("F/K çok düşük: tek seferlik kârlar veya enflasyon muhasebesi etkisi olabilir; tek başına alım nedeni değildir")
        m.update({
            "quality": r(q * 100 if q is not None else None, 0), "positives": pos, "negatives": neg,
            "sector_pe_median": r(sm.get("pe")), "sector_pb_median": r(sm.get("pb")),
            "rel_valuation": r(rel, 2), "class": cls, "class_explain": CLASS_EXPLAIN[cls],
        })
        out.append(m)
    return out


def refresh_cache(ctx, prices: dict, force_all: bool = False, limit: int | None = None) -> dict:
    """Önbellekteki eski temel verileri yeniler (her çalıştırmada en fazla 'limit' hisse)."""
    path = ctx.cfg.data_dir / "cache" / "fundamentals.json"
    cache = load_json(path, {}) or {}
    days = float(ctx.cfg.get("fundamentals", "refresh_days", default=7))
    limit = limit or int(ctx.cfg.get("fundamentals", "refresh_per_run", default=40))
    now = time.time()
    tickers = list(ctx.cfg.stocks())
    stale = [t for t in tickers if force_all or now - (cache.get(t, {}).get("fetched_at") or 0) > days * 86400]
    stale.sort(key=lambda t: cache.get(t, {}).get("fetched_at") or 0)
    todo = stale if force_all else stale[:limit]

    def fetch(t):
        ts = yahoo.fundamentals(ctx.client, t, now)
        mo = yahoo.chart(ctx.client, t, "5y", "1mo", events=True)
        return t, ts, mo.dividends if mo.ok else []

    for t, ts, divs in parallel_map(fetch, todo, ctx.workers):
        if ts.get("error") and t in cache:
            continue  # eski veriyi koru
        cache[t] = {"fetched_at": now, "ts": ts, "dividends": divs}
    if todo:
        save_json(path, cache, compact=True)
    return cache


def analyze_all(ctx, cache: dict, snaps: dict) -> list[dict]:
    cpi = {str(k): v for k, v in (ctx.cfg.macro.get("yillik_tufe") or {}).items()}
    usd = set(ctx.cfg.universe.get("usd_reporters", []))
    stocks = ctx.cfg.stocks()
    ms = []
    for t, info in stocks.items():
        entry = cache.get(t)
        if not entry:
            continue
        price = (snaps.get(t) or {}).get("price")
        m = metrics(t, entry.get("ts") or {}, entry.get("dividends") or [], price, info.get("sector") or "Diğer",
                    t in usd, cpi)
        m["name"] = (snaps.get(t) or {}).get("name", t)
        m["fetched_at"] = entry.get("fetched_at")
        ms.append(m)
    return classify_all(ms)
