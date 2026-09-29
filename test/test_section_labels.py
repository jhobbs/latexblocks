"""\\label directly after a sectioning command: the section joins the global
label index, so \\@{label} / \\dref{label} link to the heading from any page."""
import os
import tempfile

import pytest

from conftest import DictUrlMapper  # pytest puts test/ on sys.path (no __init__.py)
from latexblocks.block_index import BlockIndex
from latexblocks.latex_processor import LatexDialectError, parse_latex_file
from latexblocks.page_renderer import PageRenderer, clear_page_cache

DEFINING = r"""\title{Outer Measure}

\section{Outer Measure}

\subsection{Good Properties of Outer Measure}\label{outer-measure-properties}

Some text.
"""

REFERENCING = r"""\title{Uses}

See \@{outer-measure-properties}, the \@[nice properties]{outer-measure-properties},
and \dref{section:outer-measure-properties}; not \@{theorem:outer-measure-properties}.
"""


def parse(src):
    return parse_latex_file(src, "content/t.tex")[1]


def _build(files):
    for path, text in files.items():
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)
    mapping = {p[len("content/"):-len(".tex")] + "/": p for p in files}
    clear_page_cache()
    mapper = DictUrlMapper(mapping)
    index = BlockIndex(mapper)
    index.build_index()
    return index, PageRenderer(mapper, index)


def _in_tmp(fn):
    old = os.getcwd()
    with tempfile.TemporaryDirectory() as tmp:
        os.chdir(tmp)
        try:
            fn()
        finally:
            os.chdir(old)
            clear_page_cache()


def test_parse_records_section_label():
    doc = parse(DEFINING)
    assert [(s.label, s.title, s.heading_id) for s in doc.sections] == [
        ("outer-measure-properties", "Good Properties of Outer Measure",
         "good-properties-of-outer-measure")]
    html = "".join(i for i in doc.items if isinstance(i, str))
    assert '<h2 id="good-properties-of-outer-measure">Good Properties of Outer Measure</h2>' in html
    assert "outer-measure-properties" not in html


def test_label_on_next_line_after_section():
    doc = parse("\\subsection{A B}\n\\label{ab}\n\ntext")
    assert [s.label for s in doc.sections] == ["ab"]


def test_label_not_after_section_is_loud():
    with pytest.raises(LatexDialectError, match=r"t\.tex:3: \\label"):
        parse("\\subsection{A}\n\nSome text \\label{x}\n")


def test_duplicate_section_label_in_file_is_loud():
    with pytest.raises(LatexDialectError, match=r"t\.tex:2: .*'ab'"):
        parse("\\section{A}\\label{ab}\n\\section{B}\\label{ab}\n")


def test_section_references_end_to_end():
    def run():
        _, renderer = _build({"content/measure/outer.tex": DEFINING,
                              "content/uses.tex": REFERENCING})
        html = renderer.render_page("content/uses.tex")["content"]
        url = "/mathnotes/measure/outer/#good-properties-of-outer-measure"
        link = (f'<a href="{url}" class="section-reference" data-ref-type="section" '
                f'data-ref-label="outer-measure-properties">')
        assert f"{link}Good Properties of Outer Measure</a>" in html
        assert f"{link}nice properties</a>" in html
        assert html.count(link) == 3
        assert 'class="block-reference-error"' in html  # theorem: type mismatch
    _in_tmp(run)


def test_section_label_colliding_with_block_label_is_loud():
    def run():
        with pytest.raises(LatexDialectError, match="outer-measure-properties"):
            _build({"content/measure/outer.tex": DEFINING,
                    "content/zother.tex": "\\begin{theorem}[Outer Measure Properties] x \\end{theorem}\n"})
    _in_tmp(run)

    def run_reverse():  # same collision, other scan order
        with pytest.raises(LatexDialectError, match="outer-measure-properties"):
            _build({"content/measure/outer.tex": DEFINING,
                    "content/aother.tex": "\\begin{theorem}[Outer Measure Properties] x \\end{theorem}\n"})
    _in_tmp(run_reverse)
