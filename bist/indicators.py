"""Teknik göstergeler (saf Python, ek kütüphane gerekmez).

Tüm fonksiyonlar girdiyle aynı uzunlukta liste döndürür; hesaplanamayan
(ısınma dönemi) yerlerde None bulunur.
"""
from __future__ import annotations

import math


def last(xs, default=None):
    for x in reversed(xs or []):
        if x is not None:
            return x
    return default


def sma(xs: list[float], n: int) -> list:
    out = [None] * len(xs)
    s = 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(xs: list[float], n: int) -> list:
    out = [None] * len(xs)
    if len(xs) < n or n <= 0:
        return out
    k = 2 / (n + 1)
    prev = sum(xs[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(xs)):
        prev = xs[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes: list[float], n: int = 14) -> list:
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        gains += max(d, 0)
        losses += max(-d, 0)
    ag, al = gains / n, losses / n

    def val(ag, al):
        if al == 0:
            return 100.0 if ag > 0 else 50.0
        return 100 - 100 / (1 + ag / al)

    out[n] = val(ag, al)
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(d, 0)) / n
        al = (al * (n - 1) + max(-d, 0)) / n
        out[i] = val(ag, al)
    return out


def macd(closes: list[float], fast: int = 12, slow: int = 26, sig: int = 9):
    ef, es = ema(closes, fast), ema(closes, slow)
    line = [None if (a is None or b is None) else a - b for a, b in zip(ef, es)]
    start = next((i for i, x in enumerate(line) if x is not None), None)
    signal = [None] * len(closes)
    if start is not None:
        sub = ema([x for x in line[start:]], sig)
        for j, x in enumerate(sub):
            signal[start + j] = x
    hist = [None if (a is None or b is None) else a - b for a, b in zip(line, signal)]
    return line, signal, hist


def true_range(h, l, c) -> list:
    out = [None] * len(c)
    for i in range(len(c)):
        if i == 0:
            out[i] = h[i] - l[i]
        else:
            out[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return out


def atr(h, l, c, n: int = 14) -> list:
    tr = true_range(h, l, c)
    out = [None] * len(c)
    if len(c) < n:
        return out
    prev = sum(tr[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(c)):
        prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


def bollinger(closes, n: int = 20, k: float = 2.0):
    mid = sma(closes, n)
    up, lo = [None] * len(closes), [None] * len(closes)
    for i in range(n - 1, len(closes)):
        w = closes[i - n + 1:i + 1]
        m = mid[i]
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / n)
        up[i], lo[i] = m + k * sd, m - k * sd
    return mid, up, lo


def adx(h, l, c, n: int = 14):
    size = len(c)
    adx_out, pdi_out, mdi_out = [None] * size, [None] * size, [None] * size
    if size < 2 * n + 1:
        return adx_out, pdi_out, mdi_out
    tr = true_range(h, l, c)
    pdm, mdm = [0.0] * size, [0.0] * size
    for i in range(1, size):
        up, dn = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm[i] = up if (up > dn and up > 0) else 0.0
        mdm[i] = dn if (dn > up and dn > 0) else 0.0
    str_ = sum(tr[1:n + 1])
    sp = sum(pdm[1:n + 1])
    sm = sum(mdm[1:n + 1])
    dxs = []
    for i in range(n, size):
        if i > n:
            str_ = str_ - str_ / n + tr[i]
            sp = sp - sp / n + pdm[i]
            sm = sm - sm / n + mdm[i]
        pdi = 100 * sp / str_ if str_ else 0.0
        mdi = 100 * sm / str_ if str_ else 0.0
        pdi_out[i], mdi_out[i] = pdi, mdi
        dx = 100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0.0
        dxs.append(dx)
        if len(dxs) == n:
            adx_out[i] = sum(dxs) / n
        elif len(dxs) > n:
            adx_out[i] = (adx_out[i - 1] * (n - 1) + dx) / n
    return adx_out, pdi_out, mdi_out


def vwap(h, l, c, v) -> list:
    out = [None] * len(c)
    pv = vol = 0.0
    for i in range(len(c)):
        tp = (h[i] + l[i] + c[i]) / 3
        pv += tp * v[i]
        vol += v[i]
        out[i] = pv / vol if vol > 0 else None
    return out


def rolling_max(xs, n: int) -> list:
    return [max(xs[max(0, i - n + 1):i + 1]) if i >= n - 1 else None for i in range(len(xs))]


def rolling_min(xs, n: int) -> list:
    return [min(xs[max(0, i - n + 1):i + 1]) if i >= n - 1 else None for i in range(len(xs))]


def pivots(h: float, l: float, c: float) -> dict:
    """Klasik pivot noktaları (önceki günün yüksek/düşük/kapanışından)."""
    p = (h + l + c) / 3
    return {"P": p, "R1": 2 * p - l, "S1": 2 * p - h, "R2": p + (h - l), "S2": p - (h - l)}


def swing_levels(h, l, lookback: int = 120, wing: int = 3, tol: float = 0.012) -> tuple[list, list]:
    """Son 'lookback' mumdaki tepe/dip noktalarını kümeleyerek seviye listesi döndürür.

    Dönüş: (dipler, tepeler) — her biri [(seviye, dokunma_sayısı)] artan sırada.
    """
    n = len(h)
    start = max(0, n - lookback)
    highs, lows = [], []
    for i in range(start + wing, n - wing):
        if h[i] == max(h[i - wing:i + wing + 1]):
            highs.append(h[i])
        if l[i] == min(l[i - wing:i + wing + 1]):
            lows.append(l[i])

    def cluster(pts):
        pts = sorted(pts)
        groups: list[list[float]] = []
        for p in pts:
            if groups and abs(p / (sum(groups[-1]) / len(groups[-1])) - 1) <= tol:
                groups[-1].append(p)
            else:
                groups.append([p])
        return [(sum(g) / len(g), len(g)) for g in groups]

    return cluster(lows), cluster(highs)


def support_resistance(h, l, c, price: float, k: int = 2) -> dict:
    """Fiyata en yakın k destek ve k direnç (tepe/dip kümeleri + pivotlar)."""
    lows, highs = swing_levels(h, l)
    levels = [lv for lv, _ in lows] + [lv for lv, _ in highs]
    if len(c) >= 1:
        # Pivotlar, verilen serinin son (tamamlanmış) mumundan hesaplanır.
        pv = pivots(h[-1], l[-1], c[-1])
        levels += [pv["S1"], pv["S2"], pv["R1"], pv["R2"]]
    if len(c) >= 20:
        levels += [max(h[-20:]), min(l[-20:])]
    if len(c) >= 250:
        levels += [max(h[-250:]), min(l[-250:])]
    sup = sorted({round(x, 4) for x in levels if x < price * 0.998}, reverse=True)[:k]
    res = sorted({round(x, 4) for x in levels if x > price * 1.002})[:k]
    return {"supports": sup, "resistances": res}


def pct_change(a, b):
    if a is None or b is None or b == 0:
        return None
    return (a / b - 1) * 100


def weekly(series_t, o, h, l, c, v, to_date):
    """Günlük mumları ISO haftalarına toplar. to_date: ts -> date."""
    weeks = []
    key = None
    for i in range(len(c)):
        d = to_date(series_t[i])
        k = d.isocalendar()[:2]
        if k != key:
            weeks.append([o[i], h[i], l[i], c[i], v[i]])
            key = k
        else:
            w = weeks[-1]
            w[1] = max(w[1], h[i])
            w[2] = min(w[2], l[i])
            w[3] = c[i]
            w[4] += v[i]
    return weeks
