"""Ağ istemcisi: tekrar deneme, zaman aşımı, nazik hız sınırı.

Testlerde gerçek ağ yerine FixtureClient kullanılır.
"""
from __future__ import annotations

import gzip
import json
import threading
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (X11; Linux x86_64) BIST-Kisisel-Rapor/1.0"


class FetchError(Exception):
    pass


class HttpClient:
    def __init__(self, timeout: float = 20, retries: int = 3, min_interval: float = 0.15):
        self.timeout = timeout
        self.retries = retries
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._last = 0.0
        self.stats = {"requests": 0, "failures": 0, "by_host": {}}

    def _throttle(self):
        with self._lock:
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()

    def _record(self, url: str, ok: bool):
        host = url.split("/")[2] if "//" in url else url
        with self._lock:
            self.stats["requests"] += 1
            h = self.stats["by_host"].setdefault(host, {"ok": 0, "fail": 0})
            if ok:
                h["ok"] += 1
            else:
                h["fail"] += 1
                self.stats["failures"] += 1

    def get(self, url: str) -> bytes:
        last: Exception | None = None
        for attempt in range(self.retries):
            self._throttle()
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "gzip"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        data = gzip.decompress(data)
                    self._record(url, True)
                    return data
            except urllib.error.HTTPError as e:
                last = e
                if e.code in (400, 401, 403, 404, 405):
                    break
            except Exception as e:  # zaman aşımı, bağlantı hatası...
                last = e
            time.sleep(1.5 * (attempt + 1))
        self._record(url, False)
        raise FetchError(f"{url.split('?')[0]} -> {last}")

    def json(self, url: str):
        return json.loads(self.get(url).decode("utf-8"))

    def text(self, url: str) -> str:
        return self.get(url).decode("utf-8", errors="replace")


class FixtureClient:
    """Test istemcisi: URL içinde geçen anahtar kelimeye göre sabit yanıt döndürür."""

    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.calls: list[str] = []
        self.stats = {"requests": 0, "failures": 0, "by_host": {}}

    def _find(self, url: str):
        self.calls.append(url)
        self.stats["requests"] += 1
        for key, val in self.routes.items():
            if key in url:
                if isinstance(val, Exception):
                    self.stats["failures"] += 1
                    raise val
                return val(url) if callable(val) else val
        self.stats["failures"] += 1
        raise FetchError(f"fixture yok: {url}")

    def json(self, url: str):
        v = self._find(url)
        return json.loads(v) if isinstance(v, (str, bytes)) else v

    def text(self, url: str) -> str:
        v = self._find(url)
        return v.decode() if isinstance(v, bytes) else str(v)
