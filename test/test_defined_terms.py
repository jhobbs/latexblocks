"""\\term: further terms a definition block defines, each with its own label,
synonyms, and auto plurals/singulars, indexed as references that land on
the term inside the defining block."""
import os
import tempfile

import pytest

from conftest import DictUrlMapper  # pytest puts test/ on sys.path (no __init__.py)
from latexblocks.block_index import BlockIndex
from latexblocks.latex_processor import LatexDialectError, parse_latex_file
from latexblocks.page_renderer import PageRenderer, clear_page_cache

DEFINING = r"""\title{Statistics}

\begin{definition}[Estimator]
An \textbf{estimator} is a statistic $T$. Its value $T(x)$ is called an
\term[point estimate]{estimate}.
\end{definition}
"""

REFERENCING = r"""\title{Uses}

We compute an \@{estimate}, then more \@{estimates}, a \@{point-estimate},
and use the \@{estimator}.

\begin{remark}
Every \@{estimate} is random.
\end{remark}
"""


def parse(src):
    return parse_latex_file(src, "content/t.tex")[1].top_blocks()


def test_parse_collects_terms():
    (d,) = parse(DEFINING)
    assert [(t.title, t.label, t.synonyms) for t in d.terms] == [
        ("estimate", "estimate", [("point estimate", "point-estimate")])]
    assert '<strong class="defined-term" id="estimate">estimate</strong>' in d.body_html
    auto = [lbl for _, lbl in d.terms[0].auto_generated_synonyms]
    assert "estimates" in auto and "point-estimates" in auto
    # the block's own title keeps its own plural
    assert ("Estimators", "estimators") in d.auto_generated_synonyms


def test_term_outside_definition_is_error():
    with pytest.raises(LatexDialectError, match=r"t\.tex:\d+: \\term is only supported"):
        parse(r"\begin{theorem}[X] an \term{estimate} \end{theorem}")
    with pytest.raises(LatexDialectError, match="only supported"):
        parse(r"Page prose \term{estimate}.")


def test_term_in_nested_non_definition_is_error():
    src = (r"\begin{definition}[A] a \begin{note} \term{b} \end{note} \end{definition}")
    with pytest.raises(LatexDialectError, match="only supported"):
        parse(src)


def test_duplicate_term_in_block_is_error():
    with pytest.raises(LatexDialectError, match="more than once"):
        parse(r"\begin{definition}[A] \term{b} and \term{B} \end{definition}")


def test_term_with_math():
    (d,) = parse(r"\begin{definition}[Measurable Space] a \term{$\sigma$-algebra} \end{definition}")
    assert d.terms[0].title == "$\\sigma$-algebra"
    assert d.terms[0].label == "sigma-algebra"


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


def test_term_references_end_to_end():
    def run():
        index, renderer = _build({"content/stats.tex": DEFINING,
                                  "content/uses.tex": REFERENCING})
        html = renderer.render_page("content/uses.tex")["content"]
        url = "/mathnotes/stats/#estimate"
        assert f'<a href="{url}" class="block-reference" data-ref-type="definition" ' \
               f'data-ref-label="estimate">estimate</a>' in html
        assert f'href="{url}" class="block-reference synonym-reference" ' \
               f'data-ref-type="definition" data-ref-label="estimates">estimates</a>' in html
        assert 'data-ref-label="point-estimate">point estimate</a>' in html
        assert 'href="/mathnotes/stats/#estimator"' in html

        tip = renderer.render_page("content/uses.tex")["tooltip_data"]
        assert tip["estimate"]["defined_in"] == "Estimator"
        assert tip["estimate"]["synonym_title"] == "estimate"
        assert tip["estimate"]["synonym_of"] is None
        assert tip["point-estimate"]["synonym_of"] == "estimate"
        assert "defined_in" not in tip["estimator"]
        # the tooltip copy must not duplicate the term's anchor id
        assert 'id="estimate"' not in tip["estimate"]["content"]

        # term references count toward the defining block's panel
        block = index.get_reference("estimator").block
        assert "(also defines: estimate)" in block.rendered_html
        assert 'id="estimate"' in block.rendered_html
        refs = index.reverse_index.get_references_for_label("estimator").direct_references
        assert {r.source_label for r in refs} == {None, "remark-1"}
    _in_tmp(run)


def test_term_label_collision_is_error():
    def run():
        with pytest.raises(LatexDialectError, match="estimate"):
            _build({"content/stats.tex": DEFINING,
                    "content/zother.tex": "\\begin{definition}[Estimate] x \\end{definition}\n"})
    _in_tmp(run)
    def run_reverse():  # same collision, other scan order
        with pytest.raises(LatexDialectError, match="estimate"):
            _build({"content/stats.tex": DEFINING,
                    "content/aother.tex": "\\begin{definition}[Estimate] x \\end{definition}\n"})
    _in_tmp(run_reverse)


def test_synonym_references_count_toward_block_panel():
    def run():
        index, _ = _build({
            "content/a.tex": "\\begin{definition}[Expected Value]\\synonyms{expectation} x \\end{definition}\n",
            "content/b.tex": "\\begin{theorem}[T] an \\@{expectation} \\end{theorem}\n"})
        refs = index.reverse_index.get_references_for_label("expected-value").direct_references
        assert [r.source_label for r in refs] == ["t"]
    _in_tmp(run)
