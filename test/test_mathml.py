"""Tests for the LaTeX->MathML worker (src/latexblocks/assets/tex2mml-worker.mjs)
and the MathConverter client (latexblocks/mathml.py).

Run: ./dev.sh pytest test/test_mathml.py -q
"""
import json
import os, sys, traceback
import subprocess

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "src", "latexblocks", "assets")
WORKER = os.path.join(ASSETS, "tex2mml-worker.mjs")
from latexblocks.assets import default_sty_path
STY = str(default_sty_path())


def worker_roundtrip(requests):
    proc = subprocess.run(
        ["node", WORKER, STY],
        input="".join(json.dumps(r) + "\n" for r in requests),
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    return [json.loads(line) for line in proc.stdout.splitlines()]


def test_worker_inline_and_display():
    r1, r2 = worker_roundtrip([
        {"id": 1, "latex": "x<y", "display": False},
        {"id": 2, "latex": "\\int_0^1 f", "display": True},
    ])
    assert r1["id"] == 1 and r1["mathml"].startswith("<math")
    assert 'alttext="x&lt;y"' in r1["mathml"]
    assert 'display="block"' not in r1["mathml"]
    assert "\n" not in r1["mathml"]  # single-line output
    assert r2["id"] == 2 and 'display="block"' in r2["mathml"]
    assert 'alttext="\\int_0^1 f"' in r2["mathml"]


def test_worker_escapes_gt_in_alttext():
    r1, = worker_roundtrip([{"id": 1, "latex": "x > 0", "display": False}])
    assert 'alttext="x &gt; 0"' in r1["mathml"]
    assert 'alttext="x > 0"' not in r1["mathml"]


def test_worker_sty_macros_and_ams_symbols():
    r1, r2, r3, r4 = worker_roundtrip([
        {"id": 1, "latex": "\\vec{F}", "display": False},   # mathnotes.sty macro
        {"id": 2, "latex": "\\square", "display": False},   # ams symbol (proof QED)
        {"id": 3, "latex": "\\Res_{z=i} f(z)", "display": False},  # \operatorname* macro
        {"id": 4, "latex": "\\cancel{(x-r_1)}", "display": False},  # cancel package (eagerly loaded)
    ])
    assert "error" not in r1 and 'mathvariant="bold"' in r1["mathml"]
    assert "error" not in r2 and r2["mathml"].startswith("<math")
    assert "error" not in r3 and ">Res<" in r3["mathml"]
    assert "error" not in r4 and r4["mathml"].startswith("<math")


def test_worker_amsmath_environments():
    reqs = [{"id": i, "latex": t, "display": True} for i, t in enumerate([
        "\\begin{aligned} a &= b \\\\ c &= d \\end{aligned}",
        "\\begin{bmatrix} 1 & 2 \\\\ 3 & 4 \\end{bmatrix}",
        "\\begin{pmatrix} 1 \\\\ 2 \\end{pmatrix}",
        "\\begin{vmatrix} a & b \\\\ c & d \\end{vmatrix}",
        "\\begin{cases} 1 & x > 0 \\\\ 0 & x \\le 0 \\end{cases}",
    ])]
    for r in worker_roundtrip(reqs):
        assert "error" not in r, r


def test_worker_tex_error_is_response_not_crash():
    r1, r2 = worker_roundtrip([
        {"id": 1, "latex": "\\notarealmacro", "display": False},
        {"id": 2, "latex": "x", "display": False},
    ])
    assert "Undefined control sequence" in r1["error"]
    assert r2["mathml"].startswith("<math")  # worker survived the TeX error


def test_worker_tag_rewrites_mlabeledtr():
    # \tag{} -> mlabeledtr, which is not MathML Core (Chrome shatters it).
    # The worker rewrites it to a plain mtr with the label cell moved last.
    import re
    (r,) = worker_roundtrip([{"id": 1, "latex": "\\tag{g} x = y", "display": True}])
    m = r["mathml"]
    assert "mlabeledtr" not in m
    assert 'class="math-tagged"' in m  # on the enclosing mtable, for CSS
    assert re.search(
        r'<mtr>.*<mtd class="math-tag" id="mjx-eqn:g"><mtext>\(g\)</mtext></mtd></mtr>', m)


def test_worker_cancel_rewrites_menclose():
    # menclose is not MathML Core (Chrome drops the strike); the worker
    # rewrites updiagonalstrike to an mrow struck through with CSS.
    (r,) = worker_roundtrip([{"id": 1, "latex": "\\cancel{x+1}", "display": False}])
    assert "menclose" not in r["mathml"]
    assert '<mrow class="mml-cancel">' in r["mathml"]


def test_worker_malformed_protocol_exits_nonzero():
    proc = subprocess.run(["node", WORKER, STY], input="not json\n",
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode != 0


from latexblocks.mathml import MathConverter, MathConversionError, get_converter


def test_converter_roundtrip():
    c = MathConverter(WORKER, STY)
    try:
        mml = c.convert("x^2", display=False)
        assert mml.startswith("<math") and 'alttext="x^2"' in mml
        dm = c.convert("\\sum_{n=1}^\\infty a_n", display=True)
        assert 'display="block"' in dm
    finally:
        c.close()


def test_converter_tex_error_raises():
    c = MathConverter(WORKER, STY)
    try:
        try:
            c.convert("\\notarealmacro", display=False)
            assert False, "expected MathConversionError"
        except MathConversionError as e:
            assert "notarealmacro" in str(e) or "Undefined" in str(e)
        # converter still usable after an error response
        assert c.convert("x", display=False).startswith("<math")
    finally:
        c.close()


def test_converter_restarts_dead_worker():
    c = MathConverter(WORKER, STY)
    try:
        assert c.convert("x", display=False).startswith("<math")
        c._proc.kill()
        c._proc.wait()
        # one restart + retry of the in-flight request
        assert c.convert("y", display=False).startswith("<math")
    finally:
        c.close()


def test_converter_startup_failure_names_command():
    c = MathConverter(worker_path="/nonexistent/worker.mjs")
    try:
        c.convert("x", display=False)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "worker" in str(e).lower()
    finally:
        c.close()


def test_get_converter_is_singleton():
    assert get_converter() is get_converter()


def test_worker_class_macro_and_alttext_override():
    r1, = worker_roundtrip([{
        "id": 1,
        "latex": "x \\in \\class{notation-ref notation-ref--integers}{\\mathbb{Z}}",
        "alttext": "x \\in \\integers",
        "display": False,
    }])
    assert "notation-ref--integers" in r1["mathml"], r1
    assert 'alttext="x \\in \\integers"' in r1["mathml"], r1
    assert "\\class" not in r1["mathml"].replace('alttext="', "")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn(); print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1; print(f"FAIL {fn.__name__}"); traceback.print_exc()
    print(f"{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)


def _mo(mathml, name):
    import re
    m = re.search(r'<mo[^>]*>' + name + '</mo>', mathml)
    assert m, mathml
    return m.group(0)


def test_worker_named_operator_spacing_follows_tex():
    # Browsers give an <mo> missing from their operator dictionary (inf, sup,
    # lim, max, ...) a thick space on both sides; the worker sets TeX's
    # spacing explicitly instead.
    reqs = [{"id": i, "latex": t, "display": True} for i, t in enumerate([
        "\\inf \\left\\{ x \\right\\}",   # 0: flush against a \left fence
        "\\sup \\{ x \\}",                 # 1: flush against an open brace
        "a = \\inf_{k} x_k",               # 2: embellished; = supplies its own space
        "2\\max(a,b)",                     # 3: thin after an ordinary, none before (
        "\\liminf x",                      # 4: two-word operator name
    ])]
    r = worker_roundtrip(reqs)
    assert 'lspace="0" rspace="0"' in _mo(r[0]["mathml"], "inf")
    assert 'lspace="0" rspace="0"' in _mo(r[1]["mathml"], "sup")
    assert 'lspace="0" rspace="0.1667em"' in _mo(r[2]["mathml"], "inf")
    assert 'lspace="0.1667em" rspace="0"' in _mo(r[3]["mathml"], "max")
    assert 'lspace="0" rspace="0.1667em"' in _mo(r[4]["mathml"], "lim&#x2006;inf")


def test_worker_leaves_dictionary_operators_alone():
    (r,) = worker_roundtrip([{"id": 1, "latex": "\\sum_k x = y", "display": True}])
    assert "lspace" not in r["mathml"] and "rspace" not in r["mathml"]


def _mos(mathml, text):
    import re
    return re.findall(r'<mo[^>]*>' + re.escape(text) + '</mo>', mathml)


def test_worker_vertical_bar_and_slash_spacing_follows_tex():
    # A bare | or / in the middle of an expression is an infix operator to
    # the browser (thick/medium space both sides); TeX spaces them as
    # ordinary symbols.
    reqs = [{"id": i, "latex": t, "display": False} for i, t in enumerate([
        "|A| = 0",       # 0: bars flush against A; = supplies its own space
        "x + |A|",       # 1: + supplies its own space
        "\\inf |x|",     # 2: thin space between operator and bar, carried once
        "a/b",           # 3: slash flush
    ])]
    r = worker_roundtrip(reqs)
    for mo in _mos(r[0]["mathml"], "|") + _mos(r[1]["mathml"], "|"):
        assert 'lspace="0" rspace="0"' in mo, r
    assert 'lspace="0" rspace="0"' in _mo(r[2]["mathml"], "inf")
    first_bar = _mos(r[2]["mathml"], "|")[0]
    assert 'lspace="0.1667em" rspace="0"' in first_bar
    assert 'lspace="0" rspace="0"' in _mos(r[3]["mathml"], "/")[0]


def test_worker_mid_keeps_relation_spacing():
    (r,) = worker_roundtrip([{"id": 1, "latex": "a \\mid b", "display": False}])
    assert "lspace" not in r["mathml"]


# \intertext / \shortintertext (src/latexblocks/assets/tex-intertext.mjs):
# an amsmath-style prose row inside the alignment's own mtable, laid out by
# flank columns + a column-spanning HTML block; see mathnotes
# docs/superpowers/specs/2026-10-14-intertext-design.md for the contract.

def test_worker_intertext_markup_contract():
    (r,) = worker_roundtrip([{"id": 1, "latex":
        "\\begin{align*} a &= b \\\\ \\intertext{and so, since $x<1$ we get} c &= d \\end{align*}",
        "display": True}])
    assert "error" not in r, r
    m = r["mathml"]
    assert 'class="has-intertext"' in m[:m.index(">")]  # on the root <math>
    assert '<mtable ' in m and 'width="100%"' in m and 'class="intertext"' in m
    assert 'columnalign="center right left center"' in m  # flanks are columns too
    assert m.count('<mtd class="intertext-flank"></mtd>') == 4  # 2 per equation row
    assert ('<mtr class="intertext"><mtd columnalign="left" class="intertext" columnspan="4">'
            '<mpadded width="0"><mtext><span class="intertext-text">and so, since <math>') in m
    assert '</math> we get</span></mtext></mpadded></mtd></mtr>' in m
    assert '<mo>&lt;</mo>' in m  # nested math stays escaped
    assert m.count("<math") == 2 and m.count("</math>") == 2
    assert "&#xA0;" not in m  # run boundaries are plain spaces so the prose wraps


def test_worker_intertext_variants():
    import re
    reqs = [{"id": i, "latex": t, "display": True} for i, t in enumerate([
        "\\begin{gather*} a = b \\\\ \\intertext{thus} c = d \\end{gather*}",
        "\\begin{align*} a &= b \\intertext{mid-row, no CR before} c &= d \\end{align*}",
        "\\begin{align*} f(x)^2 &= b' \\intertext{after pending items} c &= d \\end{align*}",
        "\\begin{align*} a &= b \\\\ \\intertext{last line} \\end{align*}",
        "\\begin{align*} \\intertext{first} a &= b \\end{align*}",
        "\\begin{align*} a &= b \\\\ \\shortintertext{short} c &= d \\end{align*}",
        "\\begin{align*} a &= b \\\\ \\intertext{line one\n   line two} c &= d \\end{align*}",
        "\\begin{align*} a &= b \\tag{1} \\\\ \\intertext{tagged} c &= d \\end{align*}",
        "\\begin{alignat*}{2} a &= b & c &= d \\\\ \\intertext{alignat} e &= f \\end{alignat*}",
        "\\begin{align*} a &= b \\\\ \\intertext{one} \\intertext{two} c &= d \\end{align*}",
        "\\begin{align*} a &= b \\\\ \\intertext{A \\& B, 5\\% of~this} c &= d \\end{align*}",
        "\\begin{align*} a &= b \\\\ \\intertext{a $\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}$ b} c &= d \\end{align*}",
    ])]
    rs = worker_roundtrip(reqs)
    for r in rs:
        assert "error" not in r, r
    ms = [r["mathml"] for r in rs]
    assert 'columnspan="3"' in ms[0] and 'columnalign="center center center"' in ms[0]
    assert ms[1].count("<mtr") == 3  # the row is ended for you, as amsmath does
    assert ms[2].count("<mtr") == 3 and "<msup>" in ms[2]
    assert ms[3].count("<mtr") == 2 and ms[3].endswith("last line</span></mtext></mpadded></mtd></mtr></mtable></math>")
    assert ms[4].count("<mtr") == 2 and ms[4].index('class="intertext"') < ms[4].index("<mi>a</mi>")
    assert 'class="intertext intertext-short"' in ms[5]
    assert "line one line two" in ms[6]
    # a \tag label rides in the right flank (an extra auto column would
    # overflow the display next to two 50% flanks); no mlabeledtr, and the
    # table does not get the math-tagged layout rules
    assert "mlabeledtr" not in ms[7] and "math-tagged" not in ms[7]
    assert re.search(r'<mtr><mtd class="intertext-flank"></mtd><mtd columnalign="right"><mi>a</mi></mtd>'
                     r'<mtd columnalign="left">.*?</mtd>'
                     r'<mtd id="mjx-eqn:1" class="intertext-flank math-tag" columnalign="right">'
                     r'<mtext>\(1\)</mtext></mtd></mtr>', ms[7])
    assert ms[7].count("intertext-flank") == 4
    assert 'columnspan="6"' in ms[8] and 'columnspacing="0em 0em 0em 0em 0em"' in ms[8]
    assert ms[9].count('<mtr class="intertext">') == 2 and ms[9].count("<mtr") == 4
    assert "A &amp; B, 5% of&#xA0;this" in ms[10]
    assert ms[11].count("<mtable") == 2 and ms[11].count("</mtd>") == 4 + 1 + 4 + 4  # nested cells untouched
    assert "</math> b</span></mtext></mpadded></mtd></mtr>" in ms[11]


def test_worker_intertext_invalid_uses_are_errors():
    bad = [
        "\\begin{aligned} a &= b \\\\ \\intertext{x} c &= d \\end{aligned}",
        "\\begin{align*} \\begin{split} a &= b \\\\ \\intertext{x} c &= d \\end{split} \\end{align*}",
        "\\begin{cases} 1 & x \\\\ \\intertext{x} 0 & y \\end{cases}",
        "\\begin{align*} a &= \\left( b \\intertext{x} \\right) \\end{align*}",
        "\\begin{align*} a &= {b \\intertext{x}} \\end{align*}",
        "a \\intertext{x} b",
    ]
    rs = worker_roundtrip([{"id": i, "latex": t, "display": True} for i, t in enumerate(bad)])
    for r in rs:
        assert "error" in r and "Invalid use of \\intertext" in r["error"], r
    (r,) = worker_roundtrip([{"id": 1, "display": True, "latex":
        "\\begin{align*} a &= b \\\\ \\intertext{so \\emph{very} true} c &= d \\end{align*}"}])
    assert "error" in r and "\\emph in \\intertext prose is unsupported" in r["error"], r


def test_worker_intertext_short_rows_are_padded():
    # MathJax leaves rows short; the right flank (or \tag label) must stay in
    # the flank column, else a 50%-wide cell lands in an equation column
    import re
    reqs = [{"id": i, "latex": t, "display": True} for i, t in enumerate([
        "\\begin{align*} a &= b & c &= d \\\\ \\intertext{x} e &= f \\end{align*}",
        "\\begin{align*} a &= b \\\\ \\intertext{so} c \\end{align*}",
        "\\begin{align*} a &= b & c &= d \\\\ \\intertext{x} e &= f \\tag{2} \\end{align*}",
    ])]
    for r, cells in zip(worker_roundtrip(reqs), (6, 4, 6)):
        assert "error" not in r, r
        rows = re.findall(r"<mtr>(.*?)</mtr>", r["mathml"])  # equation rows only
        assert len(rows) == 2, r["mathml"]
        for row in rows:
            tds = re.findall(r"<mtd\b[^>]*>", row)
            assert len(tds) == cells, (row, cells)
            assert tds[0] == '<mtd class="intertext-flank">' and "intertext-flank" in tds[-1]


def test_worker_intertext_gather_spacing_and_alttext_dollars():
    r1, r2, r3 = worker_roundtrip([
        {"id": 1, "latex": "\\begin{gather*} a = b \\\\ \\intertext{thus} c = d \\end{gather*}", "display": True},
        {"id": 2, "latex": "\\begin{align*} a &= b \\\\ \\intertext{$x$'s value and $y$$z$ too} c &= d \\end{align*}", "display": True},
        {"id": 3, "latex": "\\text{$x$'s}", "display": False},
    ])
    assert 'columnspacing="0em 0em"' in r1["mathml"]  # one column, two flank gaps
    # $' $& $$ in the TeX must not be expanded by the alttext insertion
    for r in (r2, r3):
        assert "error" not in r, r
        assert r["mathml"].count("<math") == r["mathml"].count("</math>")
    assert "\\intertext{$x$'s value and $y$$z$ too}" in r2["mathml"]
    assert r3["mathml"].startswith("<math alttext=\"\\text{$x$'s}\"") and r3["mathml"].count("</math>") == 1
    (r4,) = worker_roundtrip([{"id": 4, "latex": "\\text{a\nb}", "display": False}])
    assert "a&#10;b" in r4["mathml"]  # newline in alttext as a character reference


def test_worker_intertext_prose_validation():
    bad = [
        ("\\ref{eq}", "\\ref"), ("\\eqref{eq}", "\\eqref"), ("a \\\\ b", "\\\\"), ("a \\\\", "\\\\"),
        ("5% of", "bare %"), ("a & b", "bare &"), ("x_1", "bare _"), ("x^2", "bare ^"), ("#1", "bare #"),
        ("so \\emph{very}", "\\emph"),
        ("in \\class{notation-ref notation-ref--integers}{\\mathbb{Z}} we", "\\integers"),
    ]
    reqs = [{"id": i, "display": True,
             "latex": "\\begin{align*} a &= b \\\\ \\intertext{" + t + "} c &= d \\end{align*}"}
            for i, (t, _) in enumerate(bad)]
    for r, (t, frag) in zip(worker_roundtrip(reqs), bad):
        assert "error" in r and frag in r["error"], (t, r)
    # bare braces are LaTeX grouping (invisible); escaped ones are literal
    (r,) = worker_roundtrip([{"id": 1, "display": True, "latex":
        "\\begin{align*} a &= b \\\\ \\intertext{a {b} c \\{d\\} 5\\% \\#1 x\\_y $\\{e\\}$ \\(f\\)} c &= d \\end{align*}"}])
    assert "error" not in r, r
    assert '<span class="intertext-text">a b c {d} 5% #1 x_y <math>' in r["mathml"]
    assert r["mathml"].count("<math>") == 2


def test_worker_stamps_cell_alignment_for_core_engines():
    # MathML Core has no columnalign on mtable: Chromium/WebKit center every
    # cell. The worker copies each column's alignment onto its cells (the
    # stylesheet maps mtd[columnalign] to text-align); center stays unstamped.
    r1, r2, r3, r4 = worker_roundtrip([
        {"id": 1, "latex": "\\begin{aligned} a &= b \\\\ cccc &= d \\end{aligned}", "display": True},
        {"id": 2, "latex": "\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}", "display": True},
        {"id": 3, "latex": "\\begin{align*} a &= b \\tag{1} \\\\ c &= d \\end{align*}", "display": True},
        {"id": 4, "latex": "\\begin{align*} a &= b \\\\ \\intertext{t} c &= d \\end{align*}", "display": True},
    ])
    assert r1["mathml"].count('<mtd columnalign="right">') == 2
    assert r1["mathml"].count('<mtd columnalign="left">') == 2
    assert "columnalign=" not in r2["mathml"].split("<mtr>")[1]  # matrix cells untouched
    assert 'class="math-tag"' in r3["mathml"] and r3["mathml"].count('<mtd columnalign="right">') == 2
    assert r4["mathml"].count('<mtd class="intertext-flank"></mtd>') == 4  # flanks untouched
    assert r4["mathml"].count('<mtd columnalign="right">') == 2
