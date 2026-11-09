import datetime as dt
import json
from pathlib import Path

import pytest

from bist import fmt, indicators as ind, quality as Q, yahoo
from bist.risk import RiskConfig, daily_loss_ok, position_size, risk_reward
from bist.tradecal import TradingCalendar
from bist.tz import IST

ROOT = Path(__file__).resolve().parent.parent
CAL = TradingCalendar(json.loads((ROOT / "config" / "calendar.json").read_text(encoding="utf-8")))


# ---------------- göstergeler ----------------

def test_sma_ema_constant():
    xs = [10.0] * 30
    assert ind.sma(xs, 5)[-1] == pytest.approx(10)
    assert ind.ema(xs, 9)[-1] == pytest.approx(10)
    assert ind.ema(xs, 9)[7] is None and ind.ema(xs, 9)[8] == pytest.approx(10)


def test_ema_known_value():
    xs = [1, 2, 3, 4, 5, 6]
    e = ind.ema(xs, 3)
    # tohum = (1+2+3)/3 = 2; k=0.5 -> 3, 4, 5
    assert e[2] == pytest.approx(2) and e[3] == pytest.approx(3) and e[5] == pytest.approx(5)


def test_rsi_extremes_and_range():
    up = [float(i) for i in range(1, 40)]
    assert ind.rsi(up)[-1] == pytest.approx(100)
    down = list(reversed(up))
    assert ind.rsi(down)[-1] == pytest.approx(0)
    zig = [10 + (i % 2) for i in range(60)]
    v = ind.rsi(zig)[-1]
    assert 40 < v < 60


def test_atr_and_bollinger():
    h = [11.0] * 30
    l = [9.0] * 30
    c = [10.0] * 30
    assert ind.atr(h, l, c, 14)[-1] == pytest.approx(2)
    mid, up, lo = ind.bollinger(c, 20)
    assert mid[-1] == pytest.approx(10) and up[-1] == pytest.approx(10) and lo[-1] == pytest.approx(10)


def test_macd_trend_positive():
    xs = [100 * (1.01 ** i) for i in range(80)]
    line, sig, hist = ind.macd(xs)
    assert line[-1] > 0 and sig[-1] is not None


def test_adx_strong_trend():
    n = 80
    c = [100 + i for i in range(n)]
    h = [x + 0.5 for x in c]
    l = [x - 0.5 for x in c]
    a, pdi, mdi = ind.adx(h, l, c)
    assert a[-1] > 40 and pdi[-1] > mdi[-1]


def test_vwap():
    v = ind.vwap([10, 12], [10, 12], [10, 12], [100, 300])
    assert v[0] == pytest.approx(10) and v[1] == pytest.approx((1000 + 3600) / 400)


def test_pivots_and_levels():
    p = ind.pivots(110, 90, 100)
    assert p["P"] == pytest.approx(100) and p["R1"] == pytest.approx(110) and p["S1"] == pytest.approx(90)
    h = [100 + (5 if i % 20 == 10 else 0) for i in range(100)]
    l = [95 - (5 if i % 20 == 0 else 0) for i in range(100)]
    c = [97.0] * 100
    sr = ind.support_resistance(h, l, c, 97)
    assert all(x < 97 for x in sr["supports"]) and all(x > 97 for x in sr["resistances"])


# ---------------- takvim ----------------

def test_calendar_rules():
    assert CAL.status(dt.date(2026, 11, 7))[0] == "closed"  # Cumartesi
    assert CAL.status(dt.date(2026, 10, 29))[0] == "closed"  # Cumhuriyet Bayramı
    assert CAL.status(dt.date(2026, 10, 28))[0] == "half"
    assert CAL.status(dt.date(2026, 11, 10))[0] == "open"
    assert CAL.next_trading_day(dt.date(2026, 11, 6)) == dt.date(2026, 11, 9)
    assert CAL.previous_trading_day(dt.date(2026, 10, 30)) == dt.date(2026, 10, 28)
    o, c = CAL.session(dt.date(2026, 10, 28))
    assert (c.hour, c.minute) == (12, 30)
    assert CAL.phase(dt.datetime(2026, 11, 10, 9, 45, tzinfo=IST)) == "pre"
    assert CAL.phase(dt.datetime(2026, 11, 10, 14, 0, tzinfo=IST)) == "open"
    assert CAL.phase(dt.datetime(2026, 11, 10, 18, 15, tzinfo=IST)) == "post"
    assert CAL.phase(dt.datetime(2026, 11, 8, 12, 0, tzinfo=IST)) == "closed"


# ---------------- risk ----------------

def test_position_size_math():
    cfg = RiskConfig(risk_per_trade_pct=0.5, commission_pct=0.0, slippage_pct=0.0, max_position_pct=100)
    r = position_size(100000, 100, 95, cfg)
    assert r["ok"] and r["shares"] == 100  # 500 TL risk / 5 TL = 100 lot
    assert r["risk_amount"] == pytest.approx(500)


def test_position_size_includes_costs():
    cfg = RiskConfig(risk_per_trade_pct=0.5, commission_pct=0.15, slippage_pct=0.10, max_position_pct=100)
    r = position_size(100000, 100, 95, cfg)
    # hisse başı risk = 5 + 100*0.0025 + 95*0.0025 = 5.4875 -> floor(500/5.4875)=91
    assert r["shares"] == 91
    assert r["risk_amount"] <= 500


def test_position_size_caps_and_errors():
    cfg = RiskConfig(max_position_pct=25)
    r = position_size(100000, 100, 99.9, cfg)
    assert r["shares"] * 100 <= 25000 + 1e-6
    assert any("yoğunlaşma" in w for w in r["warnings"])
    assert not position_size(100000, 100, 101, cfg)["ok"]
    assert not position_size(100, 1000, 900, cfg)["ok"]
    liq = position_size(1e8, 100, 95, RiskConfig(max_position_pct=100), avg_tl_volume=1e7)
    assert any("likidite" in w.lower() for w in liq["warnings"])


def test_rr_and_daily_loss():
    assert risk_reward(100, 95, 110) == pytest.approx(2)
    assert risk_reward(100, 100, 110) is None
    ok, _ = daily_loss_ok(-1000, 0, 100000, RiskConfig(max_daily_loss_pct=1.5))
    assert ok
    ok, msg = daily_loss_ok(-1500, 0, 100000, RiskConfig(max_daily_loss_pct=1.5))
    assert not ok and "sınır" in msg


# ---------------- biçimlendirme ----------------

def test_turkish_format():
    assert fmt.num(1234.5) == "1.234,50"
    assert fmt.pct(1.234) == "+%1,23"
    assert fmt.pct(-2) == "−%2,00"
    assert fmt.pct(None) == "—"
    assert fmt.tl(2.5e9) == "2,50 mlr TL"


# ---------------- Yahoo ayrıştırma (gerçek yanıt örnekleri) ----------------

def test_parse_real_daily(fixture_json):
    s = yahoo.parse_chart(fixture_json("thyao_1d.json"), "THYAO.IS", "1d")
    assert s.ok and len(s) > 400
    assert all(h >= l for h, l in zip(s.h, s.l))
    assert s.dividends and s.dividends[0][1] > 0
    dc = yahoo.daily_change(s)
    assert dc["price"] > 0 and dc["prev"] > 0 and dc["chg"] is not None
    assert len(set(s.dates())) == len(s)  # günler tekil


def test_parse_real_intraday(fixture_json):
    s = yahoo.parse_chart(fixture_json("thyao_5m.json"), "THYAO.IS", "5m")
    assert s.ok and len(s) > 100
    days = sorted(set(s.dates()))
    assert 3 <= len(days) <= 6
    today = s.only_date(days[-1])
    assert len(today) > 50


def test_parse_error_and_symbol():
    s = yahoo.parse_chart({"chart": {"result": None, "error": {"description": "No data found"}}}, "XXXX.IS", "1d")
    assert not s.ok and "No data" in s.error
    assert yahoo.symbol_for("thyao") == "THYAO.IS"
    assert yahoo.symbol_for("^GSPC") == "^GSPC" and yahoo.symbol_for("USDTRY=X") == "USDTRY=X"


def test_parse_timeseries(fixture_json):
    ts = yahoo.parse_timeseries(fixture_json("bimas_fund.json"))
    assert ts["annual"]["TotalRevenue"] and ts["annual"]["NetIncome"]
    assert ts["trailing"].get("PbRatio") is not None
    bank = yahoo.parse_timeseries(fixture_json("akbnk_fund.json"))
    assert bank["annual"]["NetIncome"][-1]["value"] > 0


# ---------------- veri kalitesi ----------------

def _series(times, interval="5m"):
    s = yahoo.Series("X.IS", interval)
    for t in times:
        s.t.append(int(t.timestamp())); s.o.append(10); s.h.append(10.1); s.l.append(9.9); s.c.append(10); s.v.append(1000)
    return s


def test_quality_intraday_levels():
    day = dt.date(2026, 11, 10)
    o, c = CAL.session(day)
    bars = [o + dt.timedelta(minutes=5 * i) for i in range(30)]  # 10:00-12:25
    s = _series(bars)
    q, note, age = Q.assess_intraday(s, dt.datetime(2026, 11, 10, 12, 45, tzinfo=IST), o, c)
    assert q == Q.DELAYED and age == pytest.approx(15)
    q, _, _ = Q.assess_intraday(s, dt.datetime(2026, 11, 10, 13, 30, tzinfo=IST), o, c)
    assert q == Q.STALE
    q, _, _ = Q.assess_intraday(_series(bars[:2]), dt.datetime(2026, 11, 10, 10, 25, tzinfo=IST), o, c)
    assert q == Q.INCOMPLETE
    q, _, _ = Q.assess_intraday(yahoo.empty("X", "5m", "hata"), dt.datetime(2026, 11, 10, 12, 0, tzinfo=IST), o, c)
    assert q == Q.UNAVAILABLE
    full = [o + dt.timedelta(minutes=5 * i) for i in range(96)]
    q, _, _ = Q.assess_intraday(_series(full), dt.datetime(2026, 11, 10, 18, 30, tzinfo=IST), o, c)
    assert q == Q.RELIABLE


def test_quality_daily_stale_and_jump():
    days = [dt.datetime(2026, 1, 1, 9, 55, tzinfo=IST) + dt.timedelta(days=i) for i in range(100)]
    s = yahoo.Series("X.IS", "1d")
    p = 10.0
    for i, d in enumerate(days):
        if i == 90:
            p *= 1.5
        s.t.append(int(d.timestamp())); s.o.append(p); s.h.append(p * 1.01); s.l.append(p * 0.99); s.c.append(p); s.v.append(1)
    probs = Q.validate(s)
    assert probs and "sıçrama" in probs[0]
    q, _ = Q.assess_daily(s, dt.datetime(2026, 6, 1, 12, tzinfo=IST), dt.date(2026, 6, 1), None, None)
    assert q == Q.STALE


def test_quality_index_without_volume():
    day = dt.date(2026, 11, 10)
    o, c = CAL.session(day)
    s = _series([o + dt.timedelta(minutes=5 * i) for i in range(30)])
    s.v = [0] * len(s.v)
    now = dt.datetime(2026, 11, 10, 12, 45, tzinfo=IST)
    assert Q.assess_intraday(s, now, o, c)[0] == Q.INCOMPLETE          # hisse: hacim yok = eksik
    assert Q.assess_intraday(s, now, o, c, check_volume=False)[0] == Q.DELAYED  # endeks: hacim beklenmez
