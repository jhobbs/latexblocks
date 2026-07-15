import dataclasses
import os
import tempfile

import pytest

import latexblocks
from latexblocks.config import get_config, sty_path, worker_path


@pytest.fixture(autouse=True)
def restore_session_config():
    """configure() is a wholesale reset; restore the suite's config (set by
    conftest: url_prefix=/mathnotes) after every test in this file."""
    saved = dataclasses.asdict(get_config())
    yield
    latexblocks.configure(**saved)


def test_defaults():
    latexblocks.configure()  # wholesale reset — all fields at defaults
    cfg = get_config()
    assert cfg.url_prefix == ""
    assert cfg.content_dir == "content"
    assert cfg.node_modules_dir is None
    assert sty_path().endswith(os.path.join("assets", "default.sty"))
    assert worker_path().endswith(os.path.join("assets", "tex2mml-worker.mjs"))
    assert os.path.exists(sty_path()) and os.path.exists(worker_path())


def test_url_prefix_and_content_dir_flow_to_output():
    latexblocks.configure(url_prefix="/gl", content_dir="glossary")
    from latexblocks.latex_processor import parse_latex_file
    _, doc = parse_latex_file(
        "\\title{T}\n\\includegraphics{plot.png}\n", filepath="glossary/page.tex")
    html = doc.items[0]
    # content_dir stripped from the file's directory; prefix prepended
    assert 'src="/gl/plot.png"' in html


def test_configure_resets_preexpansion_cache():
    import latexblocks.latex_processor as lp
    from latexblocks.latex_processor import parse_latex_file
    parse_latex_file("\\title{T}\nhello\n", filepath="x.tex")
    assert lp._preexpansion_macros is not None
    latexblocks.configure()
    assert lp._preexpansion_macros is None


def test_custom_sty_path():
    with tempfile.TemporaryDirectory() as d:
        sty = os.path.join(d, "my.sty")
        with open(sty, "w") as f:
            f.write("% BEGIN PRE-EXPANSION MACROS\n\\def\\zz{Z}\n% END PRE-EXPANSION MACROS\n"
                    "% BEGIN MATH MACROS\n% END MATH MACROS\n")
        latexblocks.configure(sty_path=sty)
        from latexblocks.latex_processor import _load_preexpansion_macros
        assert _load_preexpansion_macros() == {"zz": "Z"}
