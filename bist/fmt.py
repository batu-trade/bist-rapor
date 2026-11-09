"""Türkçe sayı/tarih biçimlendirme."""
from __future__ import annotations

import datetime as dt
import math

from .tz import IST


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and (math.isnan(x) or math.isinf(x)))


def num(x, d: int = 2) -> str:
    if not _ok(x):
        return "—"
    s = f"{x:,.{d}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def pct(x, d: int = 2, sign: bool = True) -> str:
    if not _ok(x):
        return "—"
    pre = ""
    if sign:
        pre = "+" if x > 0 else ("−" if x < 0 else "")
    return f"{pre}%{num(abs(x) if sign else x, d)}"


def price(x) -> str:
    if not _ok(x):
        return "—"
    d = 2 if abs(x) < 1000 else (2 if abs(x) < 100000 else 0)
    return num(x, d)


def tl(x) -> str:
    if not _ok(x):
        return "—"
    a = abs(x)
    if a >= 1e9:
        return f"{num(x / 1e9, 2)} mlr TL"
    if a >= 1e6:
        return f"{num(x / 1e6, 1)} mn TL"
    return f"{num(x, 0)} TL"


def big(x) -> str:
    if not _ok(x):
        return "—"
    a = abs(x)
    if a >= 1e9:
        return f"{num(x / 1e9, 2)} mlr"
    if a >= 1e6:
        return f"{num(x / 1e6, 1)} mn"
    return num(x, 0)


def hm(d: dt.datetime | None) -> str:
    if d is None:
        return "—"
    return d.astimezone(IST).strftime("%H:%M")


def dmy_hm(d: dt.datetime | None) -> str:
    if d is None:
        return "—"
    return d.astimezone(IST).strftime("%d.%m.%Y %H:%M")


def dmy(d: dt.date | None) -> str:
    if d is None:
        return "—"
    return d.strftime("%d.%m.%Y")


GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def gun_adi(d: dt.date) -> str:
    return GUNLER[d.weekday()]


def signed(x, d: int = 1) -> str:
    """İşaretli sayı (yüzde işareti olmadan): +14,5 / −3,2"""
    if not _ok(x):
        return "—"
    pre = "+" if x > 0 else ("−" if x < 0 else "")
    return pre + num(abs(x), d)
