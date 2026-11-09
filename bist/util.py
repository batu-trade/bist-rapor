"""Küçük yardımcılar: paralel çalıştırma, güvenli JSON okuma/yazma."""
from __future__ import annotations

import json
import os
from pathlib import Path


def parallel_map(fn, items, workers: int = 1) -> list:
    items = list(items)
    if workers <= 1 or len(items) <= 1:
        return [fn(x) for x in items]
    try:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(fn, items))
    except RuntimeError:  # iş parçacığı desteklenmeyen ortamlar
        return [fn(x) for x in items]


def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def save_json(path, data, compact: bool = False) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    if compact:
        txt = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=_default)
    else:
        txt = json.dumps(data, ensure_ascii=False, indent=1, default=_default)
    tmp.write_text(txt, encoding="utf-8")
    os.replace(tmp, p)


def _default(o):
    import datetime as dt
    if isinstance(o, (dt.datetime, dt.date)):
        return o.isoformat()
    if isinstance(o, set):
        return sorted(o)
    raise TypeError(f"JSON'a çevrilemiyor: {type(o)}")


def r(x, d: int = 2):
    """JSON için yuvarla (None güvenli)."""
    if x is None:
        return None
    try:
        return round(float(x), d)
    except (TypeError, ValueError):
        return None
