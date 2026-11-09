"""Haber, KAP ile ilgili başlıklar ve makro takvim.

ÖNEMLİ KISIT: KAP (kap.org.tr) otomatik erişimi engelliyor (test edildi: erişim
hatası sayfası dönüyor) ve ücretsiz resmi bir API sunmuyor. Kullanım koşullarını
ihlal edecek şekilde kazıma YAPMIYORUZ. Bunun yerine Google Haberler'in herkese
açık RSS akışından KAP açıklamalarına dair haber BAŞLIKLARINI alıyoruz. Bunlar
KAP'ın kendisi değildir; her başlıkta kaynağı ve doğrulama için KAP bağlantısı verilir.
"""
from __future__ import annotations

import datetime as dt
import email.utils
import re
import urllib.parse
import xml.etree.ElementTree as ET

from .tz import IST

KAP_URL = "https://www.kap.org.tr/tr/"

CATEGORIES = [
    ("Finansal tablo", ["finansal rapor", "bilanço", "finansal tablo", "net kâr", "net kar", "çeyrek", "faaliyet raporu"]),
    ("Temettü", ["temettü", "kâr payı", "kar payı", "kar dağıtım", "kâr dağıtım"]),
    ("Sermaye artırımı", ["bedelsiz", "bedelli", "sermaye artırımı", "sermaye artirimi"]),
    ("Pay geri alım", ["geri alım", "geri alim", "pay alım"]),
    ("Sözleşme / ihale", ["sözleşme", "ihale", "sipariş", "yeni iş ilişkisi", "anlaşma imzaladı"]),
    ("Yatırım", ["yatırım", "tesis", "kapasite artışı", "fabrika"]),
    ("Birleşme / satın alma", ["satın alma", "satın aldı", "birleşme", "devralma", "pay devri"]),
    ("Makro / faiz", ["tcmb", "merkez bankası", "faiz kararı", "politika faizi", "ppk"]),
    ("Makro / enflasyon", ["enflasyon", "tüfe", "tüik"]),
]
POSITIVE = ["temettü", "kâr payı", "kar payı", "geri alım", "bedelsiz", "rekor", "sözleşme imzaladı", "ihale kazandı",
            "yeni iş ilişkisi", "sipariş aldı", "kapasite artışı", "kâr artışı", "net kârı arttı", "yükseldi", "onaylandı"]
NEGATIVE = ["zarar", "ceza", "soruşturma", "temerrüt", "iflas", "konkordato", "dava", "düştü", "geriledi", "iptal",
            "durdurma", "tedbir", "işlem yasağı", "haciz", "uyarı"]


def classify(title: str) -> tuple[str, str]:
    t = title.lower()
    cat = "Genel"
    for name, keys in CATEGORIES:
        if any(k in t for k in keys):
            cat = name
            break
    pos = sum(1 for k in POSITIVE if k in t)
    neg = sum(1 for k in NEGATIVE if k in t)
    if "bedelli" in t:
        neg += 0.5  # sulandırma etkisi olabilir
    if pos > neg:
        s = "olumlu"
    elif neg > pos:
        s = "olumsuz"
    else:
        s = "nötr"
    return cat, s


IMPACT = {
    "Finansal tablo": "Kâr beklentisi ve değerleme üzerinde doğrudan etkili olabilir.",
    "Temettü": "Nakit getiri; temettü tarihlerinde fiyat düzeltmesi olur.",
    "Sermaye artırımı": "Bedelsiz genelde psikolojik olarak olumlu karşılanır (şirket değeri değişmez); bedelli sulandırma yaratabilir.",
    "Pay geri alım": "Şirketin kendi hissesini alması genelde yönetimin güven işareti olarak yorumlanır.",
    "Sözleşme / ihale": "Büyüklüğü şirket gelirine göre önemliyse olumlu etki yaratabilir.",
    "Yatırım": "Uzun vadede büyüme potansiyeli; kısa vadede finansman ihtiyacı doğurabilir.",
    "Birleşme / satın alma": "Fiyatlama ve finansman koşullarına göre olumlu veya olumsuz olabilir.",
    "Makro / faiz": "Faiz kararları özellikle banka hisselerini ve genel piyasayı etkiler.",
    "Makro / enflasyon": "Enflasyon verisi faiz beklentilerini ve piyasa yönünü etkileyebilir.",
    "Genel": "Etkisi belirsiz; detay için kaynağa bakın.",
}

TICKER_RE = re.compile(r"\b[A-ZÇĞİÖŞÜ]{4,6}\b")


def parse_rss(xml_text: str) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src_el = it.find("source")
        source = (src_el.text or "").strip() if src_el is not None and src_el.text else ""
        pub = it.findtext("pubDate")
        try:
            pdt = email.utils.parsedate_to_datetime(pub).astimezone(IST) if pub else None
        except (TypeError, ValueError):
            pdt = None
        if source and title.endswith(" - " + source):
            title = title[: -len(" - " + source)]
        items.append({"title": title, "link": link, "source": source or "Google Haberler", "published": pdt})
    return items


def google_news(client, query: str) -> list[dict]:
    q = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={q}+when:2d&hl=tr&gl=TR&ceid=TR:tr"
    try:
        return parse_rss(client.text(url))
    except Exception:
        return []


def collect(ctx, since: dt.datetime, universe: set[str], max_items: int = 25) -> dict:
    queries = list(ctx.cfg.get("news_queries", default=[]) or [])
    if ctx.cfg.get("news_per_ticker_watchlist", default=True):
        queries += [f"{t} KAP" for t in ctx.cfg.watchlist]
    seen, items, errors = set(), [], 0
    for q in queries:
        got = google_news(ctx.client, q)
        if not got:
            errors += 1
        for it in got:
            key = it["title"].lower()[:90]
            if key in seen:
                continue
            seen.add(key)
            if it["published"] is None or it["published"] < since:
                continue
            cat, sent = classify(it["title"])
            tick = sorted({m for m in TICKER_RE.findall(it["title"]) if m in universe})
            items.append({
                **it, "published": it["published"].isoformat(), "category": cat, "sentiment": sent,
                "tickers": tick, "impact": IMPACT.get(cat, IMPACT["Genel"]),
                "kap_related": "KAP" in it["title"] or cat not in ("Genel", "Makro / faiz", "Makro / enflasyon"),
            })
    items.sort(key=lambda x: x["published"], reverse=True)
    status = "çalışıyor" if items or errors < len(queries) else "erişilemedi"
    return {
        "items": items[:max_items], "status": status, "queries": len(queries), "failed_queries": errors,
        "source": "Google Haberler RSS (yalnızca başlık ve bağlantı). KAP'ın kendisi değildir; doğrulamak için kap.org.tr",
    }


def macro_calendar(ctx, days: int = 10) -> list[dict]:
    today = ctx.today
    out = []
    macro = ctx.cfg.macro or {}
    for d in macro.get("ppk_toplantilari", []):
        try:
            dd = dt.date.fromisoformat(d)
        except ValueError:
            continue
        if 0 <= (dd - today).days <= days:
            out.append({"date": dd.isoformat(), "time": "14:00", "event": "TCMB Para Politikası Kurulu faiz kararı",
                        "impact": "Faiz kararı tüm piyasayı, özellikle bankaları etkiler."})
    # TÜFE: her ayın 3'ü 10:00, hafta sonuysa ilk iş günü
    for k in range(0, 2):
        y, m = today.year, today.month + k
        if m > 12:
            y, m = y + 1, m - 12
        dd = dt.date(y, m, 3)
        while dd.weekday() >= 5:
            dd += dt.timedelta(days=1)
        if 0 <= (dd - today).days <= days:
            out.append({"date": dd.isoformat(), "time": "10:00", "event": "TÜİK aylık enflasyon (TÜFE) açıklaması",
                        "impact": "Beklentiden yüksek enflasyon faiz indirimi beklentilerini zayıflatabilir."})
    out.sort(key=lambda x: (x["date"], x["time"]))
    upd = macro.get("guncelleme")
    if upd:
        try:
            age = (today - dt.date.fromisoformat(upd)).days
            if age > 45:
                out.append({"date": today.isoformat(), "time": "", "event": "Uyarı: makro ayar dosyası güncel değil",
                            "impact": f"config/macro.json {age} gündür güncellenmedi (PPK tarihleri ve enflasyon verisi)."})
        except ValueError:
            pass
    return out
