"""Risk yönetimi: stop mesafesine göre pozisyon büyüklüğü, maliyet, likidite ve yoğunlaşma uyarıları.

Gerçek emir gönderimi YOKTUR. Bu modül yalnızca hesap yapar.
"""
from __future__ import annotations

from . import fmt
import math
from dataclasses import dataclass


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 0.5
    max_daily_loss_pct: float = 1.5
    commission_pct: float = 0.15
    slippage_pct: float = 0.10
    max_position_pct: float = 25.0
    max_adv_participation_pct: float = 1.0

    @classmethod
    def from_settings(cls, settings: dict) -> "RiskConfig":
        d = (settings or {}).get("risk", {}) or {}
        return cls(**{k: float(v) for k, v in d.items() if k in cls.__dataclass_fields__})

    @property
    def cost_rate(self) -> float:
        """Tek yön toplam maliyet oranı (komisyon + kayma)."""
        return (self.commission_pct + self.slippage_pct) / 100


def risk_reward(entry: float, stop: float, target: float) -> float | None:
    risk = entry - stop
    if risk <= 0:
        return None
    return (target - entry) / risk


def position_size(capital: float, entry: float, stop: float, cfg: RiskConfig,
                  avg_tl_volume: float | None = None) -> dict:
    """Stop mesafesine göre lot hesabı (yalnızca alış yönlü)."""
    warnings: list[str] = []
    if capital <= 0 or entry <= 0 or stop <= 0:
        return {"ok": False, "shares": 0, "warnings": ["Geçersiz sermaye/fiyat"]}
    if stop >= entry:
        return {"ok": False, "shares": 0, "warnings": ["Stop seviyesi giriş fiyatının altında olmalı"]}
    c = cfg.cost_rate
    risk_per_share = (entry - stop) + entry * c + stop * c
    risk_budget = capital * cfg.risk_per_trade_pct / 100
    shares = math.floor(risk_budget / risk_per_share)
    max_by_position = math.floor(capital * cfg.max_position_pct / 100 / (entry * (1 + c)))
    if shares > max_by_position:
        shares = max_by_position
        warnings.append(f"Pozisyon, sermayenin %{cfg.max_position_pct:g} sınırına göre küçültüldü (yoğunlaşma riski)")
    if shares <= 0:
        return {"ok": False, "shares": 0, "risk_per_share": risk_per_share,
                "warnings": ["Bu stop mesafesi için sermaye yetersiz; en az 1 lot bile risk sınırını aşıyor"]}
    value = shares * entry
    if avg_tl_volume:
        part = value / avg_tl_volume * 100
        if part > cfg.max_adv_participation_pct:
            warnings.append(f"Düşük likidite: pozisyon günlük ortalama işlem hacminin %{fmt.num(part, 2)}'i")
    stop_pct = (entry - stop) / entry * 100
    if stop_pct < 0.4:
        warnings.append("Stop çok yakın: normal fiyat oynaklığında kolayca tetiklenebilir")
    if stop_pct > 12:
        warnings.append("Stop çok uzak: tek işlemde büyük fiyat hareketi riski")
    return {
        "ok": True,
        "shares": shares,
        "position_value": round(value, 2),
        "risk_amount": round(shares * risk_per_share, 2),
        "risk_per_share": round(risk_per_share, 4),
        "cost_estimate": round(shares * (entry + stop) * c, 2),
        "stop_pct": round(stop_pct, 2),
        "position_pct": round(value / capital * 100, 2),
        "warnings": warnings,
    }


def daily_loss_ok(realized_today: float, unrealized: float, capital: float, cfg: RiskConfig) -> tuple[bool, str]:
    loss = -(realized_today + unrealized)
    limit = capital * cfg.max_daily_loss_pct / 100
    if loss >= limit:
        return False, f"Günlük zarar sınırına ulaşıldı (%{cfg.max_daily_loss_pct:g} = {limit:,.0f} TL). Bugün yeni işlem yok."
    return True, ""


def concentration_warnings(weights: dict[str, float], single_max: float = 25.0, sector_weights: dict | None = None,
                           sector_max: float = 40.0) -> list[str]:
    out = []
    for k, w in weights.items():
        if w > single_max:
            out.append(f"{k} portföyün %{fmt.num(w, 0)}'i: tek hissede yoğunlaşma riski (öneri: en fazla %{single_max:g})")
    for k, w in (sector_weights or {}).items():
        if w > sector_max:
            out.append(f"{k} sektörü portföyün %{fmt.num(w, 0)}'i: sektör yoğunlaşması")
    return out


def capital_plan(settings: dict, total: float | None = None) -> dict:
    split = (settings or {}).get("capital_split_pct", {}) or {}
    s = sum(split.values()) or 100
    out = {k: v / s * 100 for k, v in split.items()}
    if total:
        out = {k: {"pct": round(p, 1), "tl": round(total * p / 100, 0)} for k, p in out.items()}
    return out
