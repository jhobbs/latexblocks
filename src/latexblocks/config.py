"""Library-wide configuration and module-state reset.

latexblocks keeps deliberate module-level state: the parse cache
(content_loader._tex_cache), the page-render cache (page_renderer._render_cache),
the notation registry (notation._registry), the pre-expansion macro table
(latex_processor._preexpansion_macros), and the MathML worker singleton
(mathml._converter). configure() replaces the config and resets all of it,
so call it once at application startup, before any parsing.
"""
import dataclasses
from typing import Optional


@dataclasses.dataclass(frozen=True)
class Config:
    # Prepended to every canonical URL the library emits, as
    # f"{url_prefix}/{canonical_url}". mathnotes: "/mathnotes"; a site
    # serving at the root uses "". No trailing slash (normalized away at
    # configure() time).
    url_prefix: str = ""
    # Scan root (cwd-relative or absolute) for BlockIndex.build_index and
    # the notation registry; also the prefix stripped from file paths when
    # deriving display titles and image URLs.
    content_dir: str = "content"
    # Macro package: PRE-EXPANSION MACROS (parser), MATH MACROS names
    # (notation collision check), MATH MACROS expansions (MathML worker).
    # None -> the packaged assets/default.sty.
    sty_path: Optional[str] = None
    # Node worker script. None -> the packaged assets/tex2mml-worker.mjs.
    worker_path: Optional[str] = None
    # Directory whose node_modules/ provides the mathjax npm package the
    # worker requires. None -> the worker process's cwd (both consumers run
    # builds from a directory that has node_modules).
    node_modules_dir: Optional[str] = None
    # Default output path for notation.write_notation_sty().
    notation_sty_path: str = "latex/mathnotes-notation.sty"


_config = Config()


def get_config() -> Config:
    return _config


def configure(**kwargs) -> Config:
    """Replace the configuration WHOLESALE: omitted kwargs revert to their
    defaults (a reset, not a merge — reconstruct the full call to change
    one field). Also resets every module-level cache/singleton."""
    global _config
    _config = Config(**kwargs)
    if _config.url_prefix.endswith("/"):
        _config = dataclasses.replace(_config, url_prefix=_config.url_prefix.rstrip("/"))
    reset_state()
    return _config


def reset_state() -> None:
    """Clear every module-level cache/singleton (worker included)."""
    from . import latex_processor, mathml, notation
    from .content_loader import clear_content_cache
    from .page_renderer import clear_page_cache

    notation.reset_registry()
    clear_content_cache()
    clear_page_cache()
    latex_processor.clear_preexpansion_cache()
    mathml.reset_converter()


def sty_path() -> str:
    cfg = get_config()
    if cfg.sty_path is not None:
        return cfg.sty_path
    from .assets import default_sty_path
    return str(default_sty_path())


def worker_path() -> str:
    cfg = get_config()
    if cfg.worker_path is not None:
        return cfg.worker_path
    from .assets import worker_js_path
    return str(worker_js_path())
