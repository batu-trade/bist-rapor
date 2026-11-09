"""Europe/Istanbul saat dilimi yardımcıları.

Türkiye 2016'dan beri yaz/kış saati uygulamıyor (sabit UTC+3). Bu nedenle
tzdata'ya bağımlı olmadan sabit +03:00 kullanıyoruz. GitHub Actions cron
ifadeleri UTC'dir: İstanbul saati = UTC + 3.
"""
from __future__ import annotations

import datetime as dt
import os

IST = dt.timezone(dt.timedelta(hours=3), "TRT")

# Rapor dilimleri: (saat, dakika). "deadline": bu saatten sonra o rapor artık
# üretilmez ve "kaçırıldı" olarak işaretlenir (elle tetiklenirse yine üretilir).
SLOTS = {
    "premarket": {"time": (9, 45), "deadline": (10, 10), "title": "Açılış Öncesi Raporu", "short": "09:45"},
    "opening": {"time": (10, 15), "deadline": (13, 30), "title": "Açılış Sonrası Raporu", "short": "10:15"},
    "midday": {"time": (14, 0), "deadline": (17, 30), "title": "Gün Ortası Raporu", "short": "14:00"},
    "close": {"time": (18, 15), "deadline": (23, 59), "title": "Kapanış Raporu", "short": "18:15"},
}
SLOT_ORDER = ["premarket", "opening", "midday", "close"]


def now_ist() -> dt.datetime:
    """Şu anki İstanbul saati. Testler için BIST_NOW ortam değişkeni (ISO) ile sabitlenebilir."""
    fixed = os.environ.get("BIST_NOW")
    if fixed:
        d = dt.datetime.fromisoformat(fixed)
        if d.tzinfo is None:
            d = d.replace(tzinfo=IST)
        return d.astimezone(IST)
    return dt.datetime.now(IST)


def to_ist(ts: float) -> dt.datetime:
    return dt.datetime.fromtimestamp(ts, IST)


def at(day: dt.date, hm: tuple[int, int]) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, hm[0], hm[1], tzinfo=IST)


def slot_time(day: dt.date, slot: str) -> dt.datetime:
    return at(day, SLOTS[slot]["time"])


def slot_deadline(day: dt.date, slot: str) -> dt.datetime:
    return at(day, SLOTS[slot]["deadline"])


def parse_hm(s: str) -> tuple[int, int]:
    h, m = s.split(":")
    return int(h), int(m)
