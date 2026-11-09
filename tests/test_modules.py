import datetime as dt
from pathlib import Path

import pytest

from bist import fundamentals as F
from bist import news as N
from bist import paper as P
from bist import yahoo
from bist.risk import RiskConfig
from bist.state import State, due_slots, wait_seconds
from bist.tz import IST


# ---------------- durum / mükerrer önleme ----------------

def test_due_and_wait(tmp_path):
    st = State(tmp_path)
    t = lambda h, m: dt.datetime(2026, 11, 10, h, m, tzinfo=IST)
    assert due_slots(t(9, 30), st, True) == []
    assert 14 * 60 <= wait_seconds(t(9, 30), st, True) <= 15 * 60 + 10
    assert due_slots(t(9, 46), st, True) == ["premarket"]
    st.mark(dt.date(2026, 11, 10), "premarket", "ok")
    assert due_slots(t(9, 50), st, True) == []          # mükerrer üretim yok
    assert wait_seconds(t(9, 50), st, True) > 0          # 10:15'e bekle
    assert due_slots(t(10, 40), st, True) == ["opening"]  # gecikmeli tetiklemede yine üretilir
    assert due_slots(t(10, 40), st, False) == []          # tatil
    assert wait_seconds(t(7, 0), st, True) == 0           # çok erken: bekleme yok


def test_missed_marking(tmp_path):
    st = State(tmp_path)
    st.data["installed_at"] = "2026-01-01T00:00:00+03:00"
    now = dt.datetime(2026, 11, 10, 14, 30, tzinfo=IST)
    st.mark(dt.date(2026, 11, 10), "opening", "ok")
    missed = st.mark_missed(now, True)
    assert missed == ["premarket"]
    assert st.entry(dt.date(2026, 11, 10), "premarket")["status"] == "missed"
    st.save()
    assert State(tmp_path).entry(dt.date(2026, 11, 10), "premarket")["status"] == "missed"


# ---------------- simülasyon defteri ----------------

def _sig(price=100, stop=98, t1=103, t2=105):
    return {"ticker": "TEST", "price": price, "entry_low": 99.5, "entry_high": 100.5, "stop": stop, "t1": t1, "t2": t2,
            "strategy_tr": "deneme"}


def test_paper_target_then_breakeven():
    cfg = RiskConfig(commission_pct=0, slippage_pct=0, max_position_pct=100)
    led = P.new_ledger(100000, {"gun_ici": 10, "swing": 20, "uzun_vade": 50, "nakit_rezerv": 20})
    assert led["capital"]["intraday"] == 10000
    t0 = dt.datetime(2026, 11, 10, 10, 30, tzinfo=IST)
    tr, msg = P.open_trade(led, "intraday", _sig(), t0, cfg)
    assert tr is not None, msg
    assert tr["shares"] == 25  # 50 TL risk / 2 TL
    bars = [(t0 + dt.timedelta(minutes=5), 100, 103.5, 99.5, 103),   # hedef 1
            (t0 + dt.timedelta(minutes=10), 103, 103.2, 99.9, 100)]  # maliyette stop
    P.update_book(led, "intraday", {"TEST": bars}, cfg, t0 + dt.timedelta(hours=1))
    assert not led["open"] and len(led["closed"]) == 1
    c = led["closed"][0]
    assert c["exit_reason"] == "maliyette stop"
    assert c["pnl"] == pytest.approx(12 * 3)  # 12 lot hedef 1'de +3, 13 lot maliyette 0
    st = P.stats(led, "intraday")
    assert st["trades"] == 1 and st["win_rate"] == 100


def test_paper_stop_first_when_both_hit_and_gap():
    cfg = RiskConfig(commission_pct=0, slippage_pct=0, max_position_pct=100)
    led = P.new_ledger(100000, {"gun_ici": 10, "swing": 20})
    t0 = dt.datetime(2026, 11, 10, 10, 30, tzinfo=IST)
    P.open_trade(led, "intraday", _sig(), t0, cfg)
    P.update_book(led, "intraday", {"TEST": [(t0 + dt.timedelta(minutes=5), 97, 104, 96, 100)]}, cfg, t0)
    c = led["closed"][0]
    assert c["exit_reason"] == "stop" and c["exits"][0]["price"] == pytest.approx(97)  # boşlukla açılış fiyatından
    assert c["r_multiple"] < -1


def test_paper_rules():
    cfg = RiskConfig()
    led = P.new_ledger(100000, {"gun_ici": 10, "swing": 20})
    t0 = dt.datetime(2026, 11, 10, 10, 30, tzinfo=IST)
    tr, msg = P.open_trade(led, "intraday", _sig(price=110), t0, cfg)
    assert tr is None and "giriş bölgesinde" in msg
    P.open_trade(led, "intraday", _sig(), t0, cfg)
    tr, msg = P.open_trade(led, "intraday", _sig(), t0, cfg)
    assert tr is None and "zaten" in msg
    P.update_book(led, "intraday", {"TEST": []}, cfg, t0, force_close=True, last_prices={"TEST": 101})
    assert led["closed"][0]["exit_reason"] == "seans sonu"


# ---------------- haberler ----------------

def test_news_parse_and_classify(fixture_text):
    items = N.parse_rss(fixture_text("gnews.xml"))
    assert len(items) > 5
    assert all(i["title"] and i["published"] is not None for i in items)
    assert N.classify("ABC KAP: 2026 yılı kâr payı dağıtım kararı")[0] == "Temettü"
    assert N.classify("XYZ hakkında soruşturma başlatıldı")[1] == "olumsuz"
    assert N.classify("Şirket pay geri alım programı başlattı")[1] == "olumlu"
    assert N.classify("Hava güzel")[0] == "Genel"


# ---------------- temel analiz ----------------

def test_fundamental_metrics_real_fixture(fixture_json):
    ts = yahoo.parse_timeseries(fixture_json("bimas_fund.json"))
    m = F.metrics("BIMAS", ts, [], 500.0, "Perakende", False, {"2023": 64.77, "2024": 44.38, "2025": 30.89})
    assert m["revenue"] and m["net_margin"] is not None
    assert m["year"] in ("2023", "2024", "2025", "2026")
    if m["rev_growth"] is not None and m["rev_growth_real"] is not None:
        assert m["rev_growth_real"] < m["rev_growth"]  # reel büyüme nominalden düşük


def test_real_growth():
    assert F.real_growth(50, 50) == pytest.approx(0)
    assert F.real_growth(30, 44.38) < 0


def _m(t, sector, pe, pb, ni=100, roe_real=10, fcf=10, nd=0.5, g=5):
    return {"ticker": t, "sector": sector, "financial": False, "net_income": ni, "roe": roe_real + 40,
            "roe_real": roe_real, "nd_ebitda": nd, "net_debt": 10, "fcf": fcf, "rev_growth_real": g,
            "pe": pe, "pb": pb, "net_margin": 10, "net_margin_prev": 10, "ni_down_2y": False, "notes": []}


def test_classification_sector_relative():
    ms = [_m("A", "X", 5, 1, ), _m("B", "X", 10, 2), _m("C", "X", 20, 4),
          _m("D", "X", 4, 0.8, roe_real=-20, fcf=-5, g=-10, nd=5),
          _m("E", "Y", 3, 0.5)]
    out = {m["ticker"]: m["class"] for m in F.classify_all(ms)}
    assert out["A"] == "Güçlü şirket, makul değerleme"
    assert out["C"] == "Güçlü şirket ama pahalı"
    assert out["D"] == "Ucuz ama riskli"
    assert out["E"] == "İzlemeye değer"  # tek şirketli sektör: kıyas yok, ucuz diye önerilmez
    loss = F.classify_all([_m("L", "X", None, 1, ni=-5)])[0]
    assert loss["class"] == "Temelleri zayıflıyor"


def test_no_missed_before_installation(tmp_path):
    st = State(tmp_path)
    st.data["installed_at"] = "2026-11-10T12:00:00+03:00"
    st.mark(dt.date(2026, 11, 10), "opening", "missed")
    missed = st.mark_missed(dt.datetime(2026, 11, 10, 18, 0, tzinfo=IST), True)
    assert missed == ["midday"]                      # yalnızca kurulumdan sonraki rapor
    assert st.entry(dt.date(2026, 11, 10), "opening") is None
    assert st.entry(dt.date(2026, 11, 10), "premarket") is None
