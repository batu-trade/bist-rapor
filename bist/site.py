"""Statik mobil web sitesi (PWA) üretici.

Çıktı GitHub Pages'e yüklenir. Sitede yalnızca piyasa raporları ve simülasyon
sonuçları bulunur; kişisel portföy bilgisi sunucuya HİÇ gönderilmez (telefonun
tarayıcısında localStorage'da tutulur).
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import time
import zlib
from pathlib import Path

from .state import State
from .tz import SLOTS, now_ist
from .util import load_json, save_json


def _png(size: int) -> bytes:
    """Basit uygulama simgesi: koyu zemin üzerinde yükselen üç çubuk."""
    bg = (15, 23, 42, 255)
    fg = (34, 197, 94, 255)
    fg2 = (226, 232, 240, 255)
    rows = []
    pad = size // 6
    bw = (size - 2 * pad) // 5
    bars = [(pad, 0.35, fg2), (pad + 2 * bw, 0.55, fg2), (pad + 4 * bw, 0.8, fg)]
    base = size - pad
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            col = bg
            for x0, hfrac, c in bars:
                top = base - int((size - 2 * pad) * hfrac)
                if x0 <= x < x0 + bw and top <= y < base:
                    col = c
            row += bytes(col)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def build(cfg, out: Path) -> None:
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    web = cfg.root / "web"
    shutil.copytree(web, out)
    data = cfg.data_dir
    od = out / "data"
    od.mkdir(parents=True, exist_ok=True)
    # Raporlar
    index = []
    rep_dir = data / "reports"
    if rep_dir.exists():
        for day in sorted(rep_dir.iterdir(), reverse=True):
            if not day.is_dir():
                continue
            for f in sorted(day.glob("*.json")):
                rep = load_json(f)
                if not rep:
                    continue
                index.append({k: rep.get(k) for k in ("id", "slot", "title", "date", "day_name", "scheduled_for",
                                                       "generated_at", "delay_minutes", "on_time", "status", "headline",
                                                       "trigger")} | {"quality": (rep.get("data_quality") or {}).get("overall")})
        shutil.copytree(rep_dir, od / "reports")
    order = {s: i for i, s in enumerate(SLOTS)}
    index.sort(key=lambda x: (x["date"], order.get(x["slot"], 0)), reverse=True)
    save_json(od / "index.json", {"reports": index}, compact=True)
    lat = data / "latest"
    if lat.exists():
        for f in lat.glob("*.json"):
            shutil.copy(f, od / f.name)
    # Durum
    st = State(data)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    status = {
        "built_at": now_ist().isoformat(timespec="seconds"),
        "last_run": st.data.get("last_run"),
        "reports": dict(sorted(st.data["reports"].items(), reverse=True)[:14]),
        "days": dict(sorted(st.data["days"].items(), reverse=True)[:14]),
        "log": list(reversed(st.data["log"][-60:])),
        "repo": repo,
        "watchlist": cfg.watchlist,
        "schedule": {s: v["short"] for s, v in SLOTS.items()},
        "settings_public": {"risk": cfg.settings.get("risk"), "capital_split_pct": cfg.settings.get("capital_split_pct")},
        "universe_note": cfg.universe.get("_aciklama"),
    }
    save_json(od / "status.json", status, compact=True)
    # Simgeler ve önbellek sürümü
    (out / "icons").mkdir(exist_ok=True)
    for s in (180, 192, 512):
        (out / "icons" / f"icon-{s}.png").write_bytes(_png(s))
    sw = out / "sw.js"
    if sw.exists():
        sw.write_text(sw.read_text(encoding="utf-8").replace("__BUILD__", str(int(time.time()))), encoding="utf-8")
    (out / ".nojekyll").write_text("")
