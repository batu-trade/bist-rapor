"""Kağıt üzerinde (simülasyon) işlem defteri.

Gerçek para YOKTUR, emir GÖNDERİLMEZ. Gerçek portföy ile asla karıştırılmaz
(gerçek portföy yalnızca telefonunuzdaki tarayıcıda tutulur).

Kurallar:
  * Giriş: sinyalin üretildiği andaki (gecikmeli) fiyat + kayma + komisyon.
  * Çıkış: stop veya hedef; aynı mumda ikisi de görülürse STOP varsayılır (muhafazakâr).
  * Hedef 1'de pozisyonun yarısı kapanır, stop maliyete çekilir; kalan yarı hedef 2'de.
  * Gün içi pozisyonlar seans sonunda kapanır. Swing pozisyonlarda 20 işlem günü süre sınırı.
"""
from __future__ import annotations

import datetime as dt

from .risk import RiskConfig, daily_loss_ok, position_size
from .tz import IST, to_ist
from .util import load_json, r, save_json


def new_ledger(capital: float, split: dict) -> dict:
    s = sum(split.values()) or 100
    return {
        "version": 1,
        "note": "SİMÜLASYON — gerçek işlem değildir",
        "capital": {
            "intraday": round(capital * split.get("gun_ici", 10) / s, 2),
            "swing": round(capital * split.get("swing", 20) / s, 2),
        },
        "open": [],
        "closed": [],
        "equity": {"intraday": [], "swing": []},
        "next_id": 1,
    }


def load(path, settings: dict) -> dict:
    led = load_json(path)
    if not led:
        led = new_ledger(float(settings.get("paper_capital_tl", 100000)), settings.get("capital_split_pct", {}))
    return led


def save(path, ledger: dict) -> None:
    save_json(path, ledger)


def realized_on(ledger: dict, book: str, day: dt.date) -> float:
    tot = 0.0
    for t in ledger["closed"]:
        if t["book"] == book and t.get("exit_time", "")[:10] == day.isoformat():
            tot += t["pnl"]
    for t in ledger["open"]:
        if t["book"] == book:
            for ex in t.get("exits", []):
                if ex["time"][:10] == day.isoformat():
                    tot += ex["pnl"]
    return tot


def book_equity(ledger: dict, book: str) -> float:
    eq = ledger["capital"][book]
    for t in ledger["closed"]:
        if t["book"] == book:
            eq += t["pnl"]
    for t in ledger["open"]:
        if t["book"] == book:
            eq += sum(ex["pnl"] for ex in t.get("exits", []))
    return eq


def open_trade(ledger: dict, book: str, sig: dict, when: dt.datetime, cfg: RiskConfig, max_open: int = 5,
               max_per_day: int = 2) -> tuple[dict | None, str]:
    tk = sig["ticker"]
    if any(t["ticker"] == tk and t["book"] == book for t in ledger["open"]):
        return None, f"{tk} için zaten açık simülasyon pozisyonu var"
    if sum(1 for t in ledger["open"] if t["book"] == book) >= max_open:
        return None, "Açık pozisyon sınırına ulaşıldı"
    today_opened = sum(1 for t in ledger["open"] + ledger["closed"]
                       if t["book"] == book and t["entry_time"][:10] == when.date().isoformat())
    if today_opened >= max_per_day:
        return None, "Günlük yeni işlem sınırına ulaşıldı"
    capital = book_equity(ledger, book)
    ok, msg = daily_loss_ok(realized_on(ledger, book, when.date()), 0.0, ledger["capital"][book], cfg)
    if not ok:
        return None, msg
    price = sig.get("price")
    entry_ref = price
    lo, hi = sig.get("entry_low"), sig.get("entry_high")
    if lo and hi and price and not (lo * 0.997 <= price <= hi * 1.003):
        return None, "Fiyat giriş bölgesinde değil; simülasyon girişi yapılmadı"
    fill = entry_ref * (1 + cfg.slippage_pct / 100)
    size = position_size(capital, fill, sig["stop"], cfg)
    if not size.get("ok"):
        return None, "; ".join(size.get("warnings", [])) or "Pozisyon hesaplanamadı"
    sh = size["shares"]
    comm = fill * sh * cfg.commission_pct / 100
    trade = {
        "id": ledger["next_id"], "book": book, "ticker": tk, "strategy": sig.get("strategy_tr") or sig.get("setup_tr"),
        "entry_time": when.isoformat(), "entry": r(fill, 4), "shares": sh, "remaining": sh,
        "stop": sig["stop"], "stop_initial": sig["stop"], "t1": sig["t1"], "t2": sig.get("t2"),
        "risk_amount": round(sh * (fill - sig["stop"]) + comm, 2), "entry_commission": round(comm, 2),
        "exits": [], "t1_done": False,
    }
    ledger["next_id"] += 1
    ledger["open"].append(trade)
    return trade, "Simülasyon pozisyonu açıldı"


def _exit(trade: dict, shares: int, price: float, when: dt.datetime, reason: str, cfg: RiskConfig):
    fill = price * (1 - cfg.slippage_pct / 100)
    comm = fill * shares * cfg.commission_pct / 100
    entry_comm_part = trade["entry_commission"] * shares / trade["shares"]
    pnl = (fill - trade["entry"]) * shares - comm - entry_comm_part
    trade["exits"].append({"time": when.isoformat(), "shares": shares, "price": r(fill, 4), "reason": reason,
                           "pnl": round(pnl, 2)})
    trade["remaining"] -= shares


def _close(ledger: dict, trade: dict):
    pnl = sum(e["pnl"] for e in trade["exits"])
    trade["pnl"] = round(pnl, 2)
    trade["r_multiple"] = round(pnl / trade["risk_amount"], 2) if trade["risk_amount"] else None
    trade["exit_time"] = trade["exits"][-1]["time"]
    trade["exit_reason"] = trade["exits"][-1]["reason"]
    ledger["open"].remove(trade)
    ledger["closed"].append(trade)


def walk(ledger: dict, trade: dict, bars: list[tuple], cfg: RiskConfig) -> None:
    """bars: [(datetime, open, high, low, close)] giriş sonrası mumlar."""
    entry_dt = dt.datetime.fromisoformat(trade["entry_time"])
    for when, o, h, l, c in bars:
        if when <= entry_dt or trade["remaining"] <= 0:
            continue
        # Boşluklu açılış: açılış zaten stopun altındaysa açılıştan çık
        if l <= trade["stop"]:
            px = o if o < trade["stop"] else trade["stop"]
            _exit(trade, trade["remaining"], px, when, "stop" if not trade["t1_done"] else "maliyette stop", cfg)
            break
        if not trade["t1_done"] and h >= trade["t1"]:
            half = trade["remaining"] // 2 if trade["remaining"] > 1 else trade["remaining"]
            _exit(trade, half, trade["t1"], when, "hedef 1", cfg)
            trade["t1_done"] = True
            trade["stop"] = trade["entry"]
            if trade["remaining"] <= 0:
                break
        if trade["t1_done"] and trade.get("t2") and h >= trade["t2"]:
            _exit(trade, trade["remaining"], trade["t2"], when, "hedef 2", cfg)
            break
    if trade["remaining"] <= 0:
        _close(ledger, trade)


def update_book(ledger: dict, book: str, bars_by_ticker: dict, cfg: RiskConfig, now: dt.datetime,
                force_close: bool = False, max_hold_days: int = 20, last_prices: dict | None = None) -> list[dict]:
    closed_now = []
    for trade in list(ledger["open"]):
        if trade["book"] != book:
            continue
        bars = bars_by_ticker.get(trade["ticker"]) or []
        walk(ledger, trade, bars, cfg)
        if trade in ledger["open"]:
            entry_dt = dt.datetime.fromisoformat(trade["entry_time"])
            too_old = book == "swing" and len({b[0].date() for b in bars if b[0] > entry_dt}) >= max_hold_days
            if force_close or too_old:
                px = (last_prices or {}).get(trade["ticker"]) or (bars[-1][4] if bars else None)
                if px:
                    _exit(trade, trade["remaining"], px, now, "seans sonu" if force_close else "süre doldu", cfg)
                    _close(ledger, trade)
        if trade not in ledger["open"]:
            closed_now.append(trade)
    return closed_now


def mark_equity(ledger: dict, book: str, day: dt.date, last_prices: dict) -> float:
    eq = book_equity(ledger, book)
    for t in ledger["open"]:
        if t["book"] == book and t["ticker"] in last_prices:
            eq += (last_prices[t["ticker"]] - t["entry"]) * t["remaining"]
    curve = ledger["equity"].setdefault(book, [])
    if curve and curve[-1]["date"] == day.isoformat():
        curve[-1]["equity"] = round(eq, 2)
    else:
        curve.append({"date": day.isoformat(), "equity": round(eq, 2)})
    return eq


def stats(ledger: dict, book: str) -> dict:
    trades = [t for t in ledger["closed"] if t["book"] == book]
    wins = [t for t in trades if t["pnl"] > 0]
    total = sum(t["pnl"] for t in trades)
    rs = [t["r_multiple"] for t in trades if t.get("r_multiple") is not None]
    curve = [ledger["capital"][book]] + [p["equity"] for p in ledger["equity"].get(book, [])]
    peak, mdd = curve[0], 0.0
    for x in curve:
        peak = max(peak, x)
        if peak > 0:
            mdd = max(mdd, (peak - x) / peak * 100)
    return {
        "book": book, "start_capital": ledger["capital"][book], "trades": len(trades), "wins": len(wins),
        "win_rate": r(len(wins) / len(trades) * 100, 1) if trades else None,
        "total_pnl": r(total), "avg_r": r(sum(rs) / len(rs), 2) if rs else None,
        "max_drawdown_pct": r(mdd), "open": sum(1 for t in ledger["open"] if t["book"] == book),
        "equity": r(curve[-1]),
    }


def bars_from_series(series, after: dt.datetime | None = None) -> list[tuple]:
    out = []
    for t, o, h, l, c in zip(series.t, series.o, series.h, series.l, series.c):
        d = to_ist(t)
        if after is None or d > after:
            out.append((d, o, h, l, c))
    return out
