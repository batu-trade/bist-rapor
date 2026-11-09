"""Uçtan uca: sentetik piyasa verisiyle dört raporu üret, siteyi oluştur, sonuçları denetle."""
import datetime as dt
import json

from bist import config as C
from bist import reports as R
from bist.config import Context
from bist.net import FetchError, FixtureClient
from bist.site import build
from bist.state import State
from bist.tz import IST

import synth

DAY = dt.date(2026, 11, 10)  # Salı, işlem günü


def make_client(root, now_box, fixture_text, fixture_json, fail=False, breakout=()):
    cfg = C.load(root)
    routes = {
        "/v8/finance/chart/": synth.router(lambda: now_box[0], cfg.calendar, breakout, fail_all=fail),
        "fundamentals-timeseries": (FetchError("ağ yok") if fail else fixture_json("bimas_fund.json")),
        "news.google.com": (FetchError("ağ yok") if fail else fixture_text("gnews.xml")),
        "tcmb.gov.tr": (FetchError("ağ yok") if fail else fixture_text("tcmb.xml")),
    }
    return cfg, FixtureClient(routes)


def run_slot(cfg, client, now, slot):
    ctx = Context(cfg, client, now, trigger="test")
    return R.generate(ctx, slot)


def test_four_reports_and_site(tmp_root, fixture_text, fixture_json):
    now_box = [dt.datetime(2026, 11, 10, 9, 45, tzinfo=IST)]
    cfg, client = make_client(tmp_root, now_box, fixture_text, fixture_json, breakout=("THYAO", "ASELS", "GARAN"))
    times = {"premarket": (9, 46), "opening": (10, 16), "midday": (14, 2), "close": (18, 17)}
    reps = {}
    for slot, (h, m) in times.items():
        now_box[0] = dt.datetime(2026, 11, 10, h, m, tzinfo=IST)
        reps[slot] = run_slot(cfg, client, now_box[0], slot)
    for slot, rep in reps.items():
        assert rep["status"] == "ok", (slot, rep["warnings"])
        assert rep["sections"], slot
        assert rep["data_quality"]["overall"] in ("guvenilir", "gecikmeli", "eksik")
        assert rep["generated_at"].startswith("2026-11-10")
        assert rep["disclaimer"] and rep["sources"]
        for sec in rep["sections"]:
            for it in sec["items"]:
                assert it["kind"] in ("veri", "hesap", "yorum", "senaryo", "uyari")
    # 09:45 raporu bugünün fiyatını uydurmamalı: endeks tablosu önceki günün verisini göstermeli
    pre = reps["premarket"]
    assert "Açılış öncesi" in pre["headline"]
    assert len(pre["picks"]["items"]) <= 5
    # 14:00 raporunda en fazla 3+3 aday
    assert len(reps["midday"]["picks"]["items"]) <= 6
    # Rapor dosyaları ve son durum
    d = tmp_root / "data"
    for slot in times:
        assert (d / "reports" / "2026-11-10" / f"{slot}.json").exists()
    stocks = json.loads((d / "latest" / "stocks.json").read_text(encoding="utf-8"))
    assert len(stocks["items"]) >= 70
    paper = json.loads((d / "latest" / "paper.json").read_text(encoding="utf-8"))
    assert {s["book"] for s in paper["stats"]} == {"intraday", "swing"}
    # Gün içi pozisyonlar kapanışta kapatılmış olmalı
    assert not [t for t in paper["open"] if t["book"] == "intraday"]
    # Site
    out = tmp_root / "_site"
    build(cfg, out)
    idx = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
    assert [r["slot"] for r in idx["reports"]][:4] == ["close", "midday", "opening", "premarket"]
    assert (out / "index.html").exists() and (out / "icons" / "icon-192.png").read_bytes()[:4] == b"\x89PNG"
    assert "__BUILD__" not in (out / "sw.js").read_text(encoding="utf-8")


def test_data_outage_gives_honest_warning(tmp_root, fixture_text, fixture_json):
    now = dt.datetime(2026, 11, 10, 14, 1, tzinfo=IST)
    cfg, client = make_client(tmp_root, [now], fixture_text, fixture_json, fail=True)
    rep = run_slot(cfg, client, now, "midday")
    assert rep["status"] == "partial"
    assert rep["warnings"] and "alınamadı" in rep["warnings"][0]
    assert rep["picks"]["items"] == []           # veri yokken öneri yok
    assert rep["data_quality"]["overall"] == "yok"


def test_cli_auto_skips_holiday_and_duplicates(tmp_root, fixture_text, fixture_json, monkeypatch):
    from bist import __main__ as M
    monkeypatch.setattr(M, "ROOT", tmp_root)
    # Tatil günü: rapor yok, gün kaydı var
    monkeypatch.setenv("BIST_NOW", "2026-10-29T10:20:00+03:00")
    assert M.main(["run", "--slot", "auto"]) == 0
    st = State(tmp_root / "data")
    assert st.day(dt.date(2026, 10, 29))["status"] == "closed"
    assert not st.entry(dt.date(2026, 10, 29), "opening")
    # Aynı rapor ikinci kez üretilmez
    st.mark(DAY, "premarket", "ok")
    st.save()
    monkeypatch.setenv("BIST_NOW", "2026-11-10T09:50:00+03:00")
    assert M.main(["run", "--slot", "premarket"]) == 0
    assert not (tmp_root / "data" / "reports" / "2026-11-10" / "premarket.json").exists()
