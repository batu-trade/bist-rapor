"""Veri kalitesi göstergesi.

Seviyeler (iyi → kötü):
  guvenilir  : Seans kapandıktan sonra eksiksiz günlük veri; doğrulamadan geçti.
  gecikmeli  : Seans içi veri, gecikme <= 25 dk (Yahoo'da tipik ~15 dk).
  eksik      : Veri var ama yetersiz (çok az mum, hacim yok, geçmiş kısa).
  bayat      : Veri beklenenden çok eski (seans içi > 25 dk ya da önceki güne ait).
  yok        : Veri alınamadı.

Kalite düşükse sistem güven seviyesini düşürür ya da analizi atlar.
"""
from __future__ import annotations

from . import fmt
import datetime as dt

from .tz import IST

RELIABLE, DELAYED, INCOMPLETE, STALE, UNAVAILABLE = "guvenilir", "gecikmeli", "eksik", "bayat", "yok"
LABEL = {
    RELIABLE: "Güvenilir",
    DELAYED: "Gecikmeli",
    INCOMPLETE: "Eksik",
    STALE: "Bayat",
    UNAVAILABLE: "Veri yok",
}
RANK = {RELIABLE: 4, DELAYED: 3, INCOMPLETE: 2, STALE: 1, UNAVAILABLE: 0}

DELAY_OK_MIN = 25
STALE_MIN = 90


def worst(*qs: str) -> str:
    qs = [q for q in qs if q]
    return min(qs, key=lambda q: RANK[q]) if qs else UNAVAILABLE


def at_least(q: str, minimum: str) -> bool:
    return RANK.get(q, 0) >= RANK[minimum]


def validate(series, is_index: bool = False) -> list[str]:
    """Fiyat doğrulama: imkansız değerleri ve şüpheli sıçramaları işaretler."""
    probs = []
    if not series.ok:
        return probs
    for i in range(len(series.c)):
        if min(series.o[i], series.h[i], series.l[i], series.c[i]) <= 0:
            probs.append("sıfır/negatif fiyat")
            break
        if series.h[i] + 1e-9 < series.l[i]:
            probs.append("yüksek < düşük")
            break
    if series.interval == "1d" and not is_index and len(series.c) >= 2:
        # BIST'te hisse günlük fiyat limiti genelde ±%10. Daha büyük sıçrama
        # bölünme/bedelsiz gibi düzeltilmemiş kurumsal işlem olabilir.
        for i in range(max(1, len(series.c) - 60), len(series.c)):
            ch = series.c[i] / series.c[i - 1] - 1
            if abs(ch) > 0.105:
                d = dt.datetime.fromtimestamp(series.t[i], IST).strftime("%d.%m")
                probs.append(f"{d} tarihinde %{fmt.num(abs(ch) * 100, 0)} sıçrama (bölünme/bedelsiz düzeltilmemiş olabilir)")
                break
    return probs


def assess_intraday(series, now: dt.datetime, session_open: dt.datetime, session_close: dt.datetime,
                    min_bars: int = 3) -> tuple[str, str, float | None]:
    """(kalite, açıklama, gecikme_dk)."""
    if not series.ok:
        return UNAVAILABLE, f"Gün içi veri alınamadı ({series.error or 'boş'})", None
    today = series.only_date(now.date())
    if len(today) == 0:
        if now < session_open:
            return INCOMPLETE, "Seans henüz başlamadı", None
        return STALE, "Bugüne ait gün içi mum yok (veri önceki güne ait)", None
    bar_min = 5 if series.interval == "5m" else (1 if series.interval == "1m" else 15)
    last_end = today.last_time + dt.timedelta(minutes=bar_min)
    ref = min(now, session_close + dt.timedelta(minutes=10))
    age = max(0.0, (ref - last_end).total_seconds() / 60)
    mv = sum(1 for x in today.v if x == 0)
    after_close = now > session_close + dt.timedelta(minutes=15)
    if after_close:
        if last_end >= session_close - dt.timedelta(minutes=20):
            q, note = RELIABLE, "Seans tamamlandı, gün içi veri eksiksiz"
        else:
            q, note = INCOMPLETE, f"Seans sonu verisi eksik (son mum {last_end:%H:%M})"
    elif age <= DELAY_OK_MIN:
        q, note = DELAYED, f"Son mum {today.last_time:%H:%M}, yaklaşık {fmt.num(age, 0)} dk gecikmeli"
    elif age <= STALE_MIN:
        q, note = STALE, f"Veri {fmt.num(age, 0)} dk eski"
    else:
        q, note = STALE, f"Veri çok eski ({fmt.num(age, 0)} dk)"
    if q in (RELIABLE, DELAYED) and len(today) < min_bars:
        q, note = INCOMPLETE, f"Bugün yalnızca {len(today)} mum var (en az {min_bars} gerekli)"
    if q in (RELIABLE, DELAYED) and len(today) >= 4 and mv / len(today) > 0.5:
        q, note = INCOMPLETE, "Hacim verisinin çoğu eksik"
    return q, note, age if not after_close else None


def assess_daily(series, now: dt.datetime, expected_last: dt.date, session_open: dt.datetime | None,
                 session_close: dt.datetime | None, min_len: int = 60, is_index: bool = False) -> tuple[str, str]:
    if not series.ok:
        return UNAVAILABLE, f"Günlük veri alınamadı ({series.error or 'boş'})"
    last = series.dates()[-1]
    probs = validate(series, is_index=is_index)
    if last < expected_last:
        return STALE, f"Son günlük veri {last:%d.%m.%Y} (beklenen {expected_last:%d.%m.%Y})"
    if len(series) < min_len:
        return INCOMPLETE, f"Geçmiş kısa ({len(series)} gün)"
    if probs:
        return INCOMPLETE, "; ".join(probs)
    if session_open and session_close and last == now.date() and session_open <= now <= session_close + dt.timedelta(minutes=15):
        return DELAYED, "Bugünkü günlük mum henüz kapanmadı (seans sürüyor)"
    return RELIABLE, f"Son kapanış {last:%d.%m.%Y}"
