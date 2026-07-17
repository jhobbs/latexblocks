"""Paths to the packaged assets, including the browser assets (Task 5)."""
import shutil
from pathlib import Path

# These are resolved as real filesystem paths handed to node/shutil, so the
# package must be installed unpacked (a regular pip install, not a zipapp/pex
# or any zip-imported form — assets inside a zip have no real path).
_ASSETS = Path(__file__).parent / "assets"


def default_sty_path() -> Path:
    return _ASSETS / "default.sty"


def worker_js_path() -> Path:
    return _ASSETS / "tex2mml-worker.mjs"


def web_css_path() -> Path:
    return _ASSETS / "latexblocks.css"


def web_js_path() -> Path:
    return _ASSETS / "latexblocks.js"


def copy_web_assets(dest_dir) -> None:
    """Copy the browser assets (css, js, fonts/) into a site's static dir."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(web_css_path(), dest / "latexblocks.css")
    shutil.copy(web_js_path(), dest / "latexblocks.js")
    shutil.copytree(_ASSETS / "fonts", dest / "fonts", dirs_exist_ok=True)
