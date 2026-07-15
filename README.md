# latexblocks

A LaTeX-dialect content pipeline: parse `.tex` files written with amsthm-style
structured blocks (`\begin{theorem}`, `\begin{definition}`, `\begin{proof}`, ...)
directly into HTML, resolve cross-references between blocks and pages
(`\dref{label}`, `\pagelink{slug}`, `\dembed{label}`) against a global index
built across every content file, and render inline/display math to MathML
at build time via a persistent Node/MathJax worker — no client-side
typesetting, no markdown layer, one seam (`render_math()`) every math node
passes through.

## Install

```bash
pip install "latexblocks @ https://github.com/jhobbs/latexblocks/archive/refs/tags/v0.1.0.tar.gz"
```

There is no PyPI package; install from the tagged GitHub archive above.

## Runtime requirements

Parsing content that has **no math** needs nothing beyond the pip install
(`pylatexenc` is the only runtime dependency). Parsing content that contains
math additionally needs, at the moment a math node is first converted:

- `node` (>=24) on `PATH`
- the `mathjax` npm package (`^3.2.2`), resolvable either from the process's
  current working directory (`node_modules/mathjax` under cwd) or from
  `configure(node_modules_dir=...)` if the worker's cwd won't have it (e.g.
  the consumer chdirs, or the library runs from an installed location with
  no `node_modules` above it)

Both requirements are build-image concerns — provide them in whatever Docker
stage or CI runner does the content build. Never install `node`/`mathjax` on
a production host; nothing at runtime (post-build) needs either.

## Quickstart

```python
import latexblocks
from latexblocks.mapper import UrlMapper  # Protocol only; provide your own impl
from latexblocks.block_index import BlockIndex
from latexblocks.page_renderer import PageRenderer

latexblocks.configure(url_prefix="", content_dir="content")

class MyUrlMapper:
    def __init__(self, mapping):
        self.url_mappings = dict(mapping)          # canonical URL -> file path
        self._reverse = {v: k for k, v in mapping.items()}
    def get_canonical_url(self, file_path):
        return self._reverse[file_path.replace("\\", "/")]

mapper = MyUrlMapper({"algebra/groups/": "content/algebra/groups.tex"})

index = BlockIndex(mapper)
index.build_index()          # scans content_dir, renders every block once

renderer = PageRenderer(mapper, index)
page = renderer.render_page("content/algebra/groups.tex")
# page["content"], page["title"], page["metadata"], page["canonical_url"],
# page["tooltip_data"], page["has_integrated_demos"], page["page_description"]
```

Rebuilding after content changes: point `index.url_mapper` at a fresh mapper
that reflects the new file set (or mutate the same mapper's `url_mappings` in
place) and call `index.build_index()` again — it diffs label signatures from
the previous build and invalidates the page-render cache for anything
transitively affected, even files whose own mtime didn't change.

## `configure()`

`latexblocks.configure(**kwargs)` replaces the whole config (a reset, not a
merge — omitted fields revert to their default) and clears every module-level
cache and the MathML worker singleton. Call it once at startup, before any
parsing.

| Field | Default | Meaning |
|---|---|---|
| `url_prefix` | `""` | Prepended to every canonical URL as `f"{url_prefix}/{canonical_url}"`. A site served at the root uses `""`; mathnotes uses `"/mathnotes"`. |
| `content_dir` | `"content"` | Scan root for `BlockIndex.build_index()` and the notation registry pre-scan; also the prefix stripped from file paths when deriving display titles and image URLs. |
| `sty_path` | `None` | Path to the macro package (PRE-EXPANSION MACROS, MATH MACROS names, MATH MACROS expansions). `None` uses the packaged `assets/default.sty`. |
| `worker_path` | `None` | Path to the Node MathML worker script. `None` uses the packaged `assets/tex2mml-worker.mjs`. |
| `node_modules_dir` | `None` | Directory whose `node_modules/` provides the `mathjax` npm package. `None` resolves from the worker process's cwd. |
| `notation_sty_path` | `"latex/mathnotes-notation.sty"` | Default output path for `notation.write_notation_sty()` (the generated pdflatex package exposing declared `\notation` macros). |

## The `UrlMapper` protocol

Every consumer supplies a URL mapper implementing (`latexblocks/mapper.py`):

```python
class UrlMapper(Protocol):
    url_mappings: Dict[str, str]          # canonical URL -> file path
    def get_canonical_url(self, file_path: str) -> str: ...
```

`BlockIndex` and `PageRenderer` call `get_canonical_url(file_path)` while
indexing/rendering; `ref_resolver` iterates `url_mappings` to resolve bare
`\pagelink{slug}` targets. mathnotes' `ContentDiscovery` is a filesystem
crawler implementing this; the test suite's `DictUrlMapper` (`test/conftest.py`)
is the two-method minimum over a plain dict — a single-page consumer can be
that small.

## Browser contract

`latexblocks.assets.copy_web_assets(dest_dir)` copies the compiled browser
bundle into a site's static output: `latexblocks.css`, `latexblocks.js`
(IIFE, load with a single `<script defer src="...">`, no module semantics
needed), and `fonts/` (the math webfont referenced by the CSS). The bundle
is CSP-compliant — no inline scripts, no inline event handlers.

At runtime the bundle wires up two features:

- **Reference tooltips**: hover/tap targets matching
  `a.block-reference, .notation-ref[data-ref-label]` (the second half covers
  notation refs stamped onto MathML elements, where `<a>` isn't legal, so
  those need JS-driven navigation via `data-ref-url` instead of `href`).
  Tooltip content comes from a JSON island the page must emit:
  `<script type="application/json" id="tooltip-data">[...]</script>`, an
  array of objects shaped like `PageRenderer.render_page()`'s
  `tooltip_data` dict values: `label`, `type`, `title`, `content`, and
  optionally `url`, `is_synonym`, `synonym_of`, `synonym_title`.
- **Label copy-to-clipboard**: every `.block-label-ref` element is rewritten
  to a `※` mark; clicking it copies the block's original label text to the
  clipboard with transient visual feedback.

## The `.sty` contract

The packaged `assets/default.sty` (or your own `sty_path`) is the single
source of truth shared between pdflatex and the Python/Node pipeline, via
two marker-delimited sections:

- `% BEGIN PRE-EXPANSION MACROS` / `% END PRE-EXPANSION MACROS`: simple
  parameterless `\def\name{expansion}` one-liners. `latex_processor.py`
  textually expands every use before parsing, so this is the single source
  of truth for those shorthands (e.g. `\bal`/`\eal`).
- `% BEGIN MATH MACROS` / `% END MATH MACROS`: simple one-line
  `\newcommand`/`\renewcommand{\name}[n]{expansion}` definitions. The names
  feed the notation-collision check (a `\notation` declaration can't reuse
  one of these); the expansions are parsed by the MathML worker at build
  time so MathJax expands them identically to pdflatex.

Anything outside those markers is real LaTeX (packages, environments,
site-metadata no-op commands) — the library never parses it.

## Development

Everything runs through `./dev.sh` (a thin `docker run` wrapper over the
`latexblocks-dev` image — python 3.14 + node 24 — mounting the repo at
`/app`, running as your host uid so generated files aren't root-owned):

```bash
./dev.sh npm ci                 # install frontend/build tooling
./dev.sh node build.mjs         # rebuild src/latexblocks/assets/{latexblocks.js,latexblocks.css,fonts/}
./dev.sh pip install -e '.[dev]'
./dev.sh pytest -q              # 129 tests
```

The committed files under `src/latexblocks/assets/` (`latexblocks.js`,
`latexblocks.css`, `fonts/`) are build output, generated from `frontend/`
by `build.mjs`. They are built from the library's **own** frontend source
only — no third-party JS is bundled, and CI fails if the committed assets
drift from a fresh `node build.mjs` run (`git diff --exit-code
src/latexblocks/assets`). The MathML worker script
(`src/latexblocks/assets/tex2mml-worker.mjs`) ships as plain source, not a
bundle — it still requires the `mathjax` npm package from whichever
consumer's build provides it.

## Consumers

- **mathnotes** (lacunary.org): the static-site generator this library was
  extracted from; supplies `ContentDiscovery` as its `UrlMapper` and
  `url_prefix="/mathnotes"`.
- **imagining-syntax**: renders a glossary/definitions page from
  latexblocks content at Docker build time, in a build stage only — its
  runtime image never imports latexblocks or installs node.
