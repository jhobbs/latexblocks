import latexblocks.assets as assets


def test_packaged_assets_exist():
    for p in (assets.default_sty_path(), assets.worker_js_path(),
              assets.web_css_path(), assets.web_js_path()):
        assert p.exists(), p


def test_css_covers_the_emitted_contract():
    css = assets.web_css_path().read_text(encoding="utf-8")
    for cls in (".math-block", ".block-reference", ".math-tooltip",
                ".embedded-block", ".block-label-ref", ".block-references-section",
                ".mml-cancel", ".math-tag"):
        assert cls in css, cls
    assert ".math-content-toggle" not in css      # mathnotes site policy
    assert ".block-index-page" not in css         # mathnotes site policy


def test_js_binds_the_contract():
    js = assets.web_js_path().read_text(encoding="utf-8")
    assert "tooltip-data" in js
    assert "block-reference" in js
    assert "block-label-ref" in js


def test_dark_fallbacks_are_light_only():
    """Dark-mode VARIABLE fallbacks must not ship: on light-only hosts they
    flip text colors while backgrounds stay light (unreadable). Hosts supply
    their own dark values; rule-level dark blocks remain var-driven."""
    css = assets.web_css_path().read_text(encoding="utf-8")
    import re
    blocks = re.findall(
        r"@media \(prefers-color-scheme: dark\)\s*\{(.*?)\n\}", css, re.DOTALL)
    assert blocks, "expected rule-level dark blocks to remain in shipped css"
    for block in blocks:
        assert "--color-text:" not in block, "dark var fallback leaked into shipped css"


def test_copy_web_assets(tmp_path):
    assets.copy_web_assets(tmp_path)
    assert (tmp_path / "latexblocks.css").exists()
    assert (tmp_path / "latexblocks.js").exists()
    assert (tmp_path / "fonts" / "LatinModernMath-Regular.woff2").exists()
