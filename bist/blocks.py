"""Rapor yapı taşları. Her öğe bir 'kind' taşır:

  veri     : Doğrulanmış piyasa verisi (kaynaktan geldiği gibi)
  hesap    : Hesaplanmış gösterge (RSI, ATR, destek/direnç...)
  yorum    : Algoritmik yorum (kurallara dayalı değerlendirme)
  senaryo  : Olası senaryo (gerçekleşmeyebilir)
"""
from __future__ import annotations

from . import fmt
from . import quality as Q

KINDS = {
    "veri": "Doğrulanmış piyasa verisi",
    "hesap": "Hesaplanmış gösterge",
    "yorum": "Algoritmik yorum",
    "senaryo": "Olası senaryo",
    "uyari": "Uyarı",
}


def text(t: str, kind: str = "yorum") -> dict:
    return {"type": "text", "kind": kind, "text": t}


def bullets(items: list[str], kind: str = "yorum") -> dict:
    return {"type": "list", "kind": kind, "items": [i for i in items if i]}


def table(columns: list[str], rows: list[list], kind: str = "veri", note: str | None = None) -> dict:
    return {"type": "table", "kind": kind, "columns": columns, "rows": rows, "note": note}


def signals(sigs: list[dict], kind: str = "hesap") -> dict:
    return {"type": "signals", "kind": kind, "signals": sigs}


def news(items: list[dict]) -> dict:
    return {"type": "news", "kind": "veri", "items": items}


def warn(t: str) -> dict:
    return {"type": "text", "kind": "uyari", "text": t}


def section(sid: str, title: str, items: list[dict], note: str | None = None) -> dict:
    return {"id": sid, "title": title, "items": [i for i in items if i], "note": note}


def chg(x) -> dict:
    return {"t": fmt.pct(x), "c": "up" if (x or 0) > 0 else ("down" if (x or 0) < 0 else "")}


def qcell(q: str) -> dict:
    return {"t": Q.LABEL.get(q, q or "—"), "c": "q-" + (q or "yok")}


def tk(ticker: str) -> dict:
    return {"t": ticker, "link": ticker}
