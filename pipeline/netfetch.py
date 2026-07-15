"""Small stdlib-only HTTP helpers."""

import time
import urllib.request

_UA = "bazel-matrix-pipeline (+https://github.com/dan-stowell/bazel-matrix)"

def _open(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    return urllib.request.urlopen(req, timeout=timeout)

def get_text(url, timeout=30, retries=3):
    last = None
    for attempt in range(retries):
        try:
            with _open(url, timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1 + attempt)
    raise last

def get_bytes(url, timeout=120, retries=3):
    last = None
    for attempt in range(retries):
        try:
            with _open(url, timeout) as resp:
                return resp.read()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1 + attempt)
    raise last
