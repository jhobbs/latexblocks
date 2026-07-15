"""Paths to the packaged assets. Extended with web-asset helpers in Task 5."""
from pathlib import Path

_ASSETS = Path(__file__).parent / "assets"


def default_sty_path() -> Path:
    return _ASSETS / "default.sty"


def worker_js_path() -> Path:
    return _ASSETS / "tex2mml-worker.mjs"
