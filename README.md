# latexblocks

A LaTeX-dialect content pipeline: parse `.tex` files written with amsthm-style
structured blocks (`\begin{theorem}`, `\begin{definition}`, `\begin{proof}`, ...)
directly into HTML, resolve cross-references between blocks and pages
(`\dref{label}`, `\pagelink{slug}`, `\dembed{label}`) against a global index
built across every content file, and render inline/display math to MathML
at build time via a persistent Node/MathJax worker — no client-side
typesetting, no markdown layer, one seam (`render_math()`) every math node
passes through.

## The dialect by example

Blocks *chain*: a proof attaches to the theorem above it, a corollary rides the
same anchor, a definition links to the definition it builds on, and every
`\@{label}` reference resolves to a real block anywhere in the content tree.
Here is one page (`content/algebra/groups.tex`) that exercises the whole chain:

```latex
\title{Groups}

\begin{definition}[Group]\label{group}\synonyms{groups}
A \emph{group} is a set $G$ with an associative operation $\ast$ that has an
identity $e$ and gives every $g \in G$ an inverse $g^{-1}$.
\end{definition}

\begin{definition}[Abelian Group]\label{abelian-group}
An abelian group is a \@{group} whose operation also commutes:
$a \ast b = b \ast a$ for all $a, b \in G$.
\end{definition}

\begin{theorem}[Uniqueness of Inverses]\label{inverses-unique}
In an \@{abelian-group}, every element has exactly one inverse.
\end{theorem}

\begin{proof}
Suppose $h$ and $h'$ are both inverses of $g$. Then
$h = h \ast e = h \ast (g \ast h') = (h \ast g) \ast h' = e \ast h' = h'$.
\end{proof}

\begin{corollary}
The inverse map $g \mapsto g^{-1}$ is well defined.
\end{corollary}

\detach

\begin{remark}
Commutativity drove the argument, but uniqueness of inverses in fact holds in
every \@{group}.
\end{remark}

A plural \@{groups} links back to the Group definition through its registered
synonym.
```

What chains, and how:

- **`Abelian Group` → `Group`** (definition → definition). Its body writes
  `\@{group}`, so the card links to the Group definition.
- **`theorem` → `Abelian Group`** (theorem → definition). The statement writes
  `\@{abelian-group}`.
- **`proof`** sits immediately after the theorem, so it is attached *inside* the
  theorem card, gets the auto-label `proof-of-inverses-unique`, and is closed
  with an automatic QED `\square`.
- **`corollary`** follows the proof and attaches to the same theorem anchor
  (auto-labelled `corollary-5`, the running block counter).
- **`\detach`** closes that anchor, so the trailing `remark` renders as its own
  top-level card (auto-label `remark-6`) instead of being swept into the theorem.

Everything below is copied from a real run of the pipeline over that file
(`url_prefix=""`); HTML is trimmed with `...` but every class, id, and
attribute shown is exactly what the renderer emits.

### The emitted card nesting

The theorem, its proof, and its corollary render as one nested card; the
detached remark is a sibling of it:

```html
<div class="math-block math-theorem" id="inverses-unique" data-label="inverses-unique">
  <div class="math-block-header">
    <span class="math-block-type">Theorem:</span>
    <span class="math-block-title"><a href="/algebra/groups/#inverses-unique">Uniqueness of Inverses</a></span>
    <span class="block-label-ref">\@{inverses-unique}</span>
  </div>
  <div class="math-block-content">
    <p>In an <a href="/algebra/groups/#abelian-group" class="block-reference" ...>abelian group</a>, every element has exactly one inverse.</p>

    <div class="math-block math-proof math-block-nested" id="proof-of-inverses-unique" data-label="proof-of-inverses-unique">
      <div class="math-block-header"><span class="math-block-type">Proof</span> ...</div>
      <div class="math-block-content">
        <p>Suppose ...</p>
        <math ...><mi>&#x25FB;</mi></math>   <!-- auto QED \square -->
      </div>
    </div>

    <div class="math-block math-corollary math-block-nested" id="corollary-5" data-label="corollary-5">
      ...
    </div>
  </div>
</div>

<div class="math-block math-remark" id="remark-6" data-label="remark-6">   <!-- detached: not nested -->
  ...
</div>
```

Nested blocks carry the extra `math-block-nested` class; the remark does not,
because `\detach` broke the chain before it.

### What a reference renders as

`\@{abelian-group}` in the theorem body becomes an `<a>` whose text is the
target definition's title, **lowercased** for mid-sentence prose:

```html
\@{abelian-group}  →  <a href="/algebra/groups/#abelian-group" class="block-reference"
                          data-ref-type="definition" data-ref-label="abelian-group">abelian group</a>
```

The case is a feature. If you want the title-cased words, spell the reference
with that capitalization and the case is transferred onto the title verbatim
(the math inside a title is never re-cased). The four renders below are also
real resolver output, but from separate runs against the same labels — the
page above doesn't write them:

```html
\@{Abelian-Group}  →  <a ... data-ref-label="Abelian-Group">Abelian Group</a>
\@[the group axioms]{group}  →  <a ... data-ref-label="group">the group axioms</a>
\dref{theorem:inverses-unique}  →  <a ... data-ref-type="theorem" ...>Uniqueness of Inverses</a>
\dref{definition:inverses-unique}  →  <span class="block-reference-error" ...>@definition:inverses-unique</span>
```

The last line shows type validation: `theorem:` matches, `definition:` does not,
so the reference renders as a visible error rather than a silently wrong link.

### Hover-card (tooltip) data

`render_page()["tooltip_data"]` is a dict keyed by every label the page
references, carrying the content a hover card shows. Two of this page's
entries (trimmed) — note the synonym entry, keyed by the plural `groups`,
which points back at the Group definition:

```python
{
  "abelian-group": {
    "type": "definition",
    "title": "Abelian Group",
    "content": '<p>An abelian group is a <a ... data-ref-label="group">group</a> ...</p>',
    "url": "/algebra/groups/#abelian-group",
    "is_synonym": False, "synonym_of": None, "synonym_title": None,
  },
  "groups": {                        # \synonyms{groups} on the Group definition
    "type": "definition",
    "title": "Group",
    "content": "<p>A <em>group</em> is a set ...</p>",
    "url": "/algebra/groups/#group",
    "is_synonym": True, "synonym_of": "Group", "synonym_title": "groups",
  },
}
```

### The "Referenced by" panel

Because both `Abelian Group` and the theorem reach the Group definition, the
reverse index bakes a backlink panel into the Group card — direct referrers
plus transitive ones:

```html
<div class="block-references-section"><details>
  <summary>Referenced by (2 direct, 1 transitive)</summary>
  <div class="direct-references"><h4>Direct references:</h4><ul>
    <li><a href="/algebra/groups/#abelian-group">Abelian Group</a></li>
    <li><a href="/algebra/groups/#remark-6">remark-6</a></li>
  </ul></div>
  <div class="transitive-references"><h4>Transitive (depth 1):</h4><ul>
    <li><a href="/algebra/groups/#inverses-unique">Uniqueness of Inverses</a></li>
  </ul></div>
</details></div>
```

## Block types

Fourteen environments, grouped by how they chain. An *anchor* opens an
attachment context; *attachments* fall into the currently-open anchor; a
*standalone* block closes any open anchor and stands on its own.

| Environment | Behavior | Chains by |
|---|---|---|
| `definition`, `axiom`, `explanation` | **standalone** | Emitted at top level; close any open anchor. A titled `definition` auto-labels from its title and may declare `\synonyms`; `explanation` is free-standing expository prose. |
| `theorem`, `lemma`, `proposition`, `exercise` | **anchor** | Open a fresh attachment context that following proofs / notes fall into. |
| `corollary` | **attach-or-anchor** | Attaches to the open anchor if there is one; otherwise becomes an anchor itself. |
| `proof` | **attachment** → statement | Attaches inside the current `theorem`/`lemma`/`proposition`/`corollary` (or `exercise`); auto-labels `proof-of-<label>`, appends an automatic QED `\square`. Errors if no statement precedes it. |
| `solution` | **attachment** → exercise | Attaches inside the current block only when it is an `exercise`; errors otherwise. |
| `note`, `remark`, `example`, `intuition` | **attachment** → any open anchor | Attach to the open anchor if one is active, else emit standalone (never an error). |

`\detach` (a bare macro, not an environment) closes the open anchor early, so
the next attachable block starts its own card instead of joining the previous
one — as the `remark` above does.

Auto-labels: a titled definition normalizes its title (`Abelian Group` →
`abelian-group`); an attached block derives from its parent (`proof-of-…`,
`<parent>-<type>`); anything else falls back to `<type>-<counter>`.

## Dialect cheat sheet

References and page directives the parser understands (verify any of these
against `latex_processor.py`):

| Syntax | Meaning |
|---|---|
| `\@{label}` | Reference a block; auto link text from its title/snippet. Preferred shorthand — an exact alias of `\dref`. |
| `\dref{label}` | Same as `\@{label}`. |
| `\@[custom text]{label}` / `\dref[custom text]{label}` | Reference with explicit link text. |
| `\dref{type:label}` | Reference with type validation; renders a `block-reference-error` span if the target's type differs. |
| `\pagelink{slug}` / `\pagelink[text]{slug}` | Link to a page by slug, resolved through the URL mapper. |
| `\dembed{label}` | Transclude the target block's full rendered card inline. Page level only — inside a block body it can fail with an order-dependent build error if the target hasn't rendered yet. |
| `\notation{\macro}{expansion}` | At the top of a block: declare a site-wide math macro whose every use links back to this block. |
| `\synonyms{a, b}` | At the top of a **definition**: register alternate titles (also auto-plurals/singulars) as reference aliases. |
| `\tags{a, b}` | At the top of a block: attach classification chips. |
| `\label{label}` | At the top of a block: set its explicit label (else auto-generated). |
| `\title{...}`, `\description{...}`, `\slug{...}` | Page metadata (all optional; `\slug` overrides the URL derived from the path). |

Standard LaTeX also works and renders to the obvious HTML: `\section` /
`\subsection` / `\subsubsection` / `\paragraph` / `\subparagraph`,
`itemize` / `enumerate`, `tabular` (l/c/r columns), `verbatim` and
`lstlisting` (`[language=...]` becomes a `language-*` class), `\href{url}{text}`,
`\includegraphics[alt=...,width=...]{path}`, the inline styles
`\emph` / `\textit` / `\textbf` / `\texttt`, and of course math — `$...$`
inline and `\[...\]` (or the `\bal ... \eal` aligned shorthand) display.
Anything the dialect does not recognize is a loud build error with `file:line`,
never silently dropped.

## Install

```bash
pip install "latexblocks @ https://github.com/jhobbs/latexblocks/archive/refs/tags/v0.1.3.tar.gz"
```

There is no PyPI package; install from the tagged GitHub archive above.

## Runtime requirements

Python **>=3.14** is required (the pip install enforces this). Parsing content
that has **no math** needs nothing further (`pylatexenc` is the only runtime
dependency). Parsing content that contains math additionally needs, at the
moment a math node is first converted:

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
| `url_prefix` | `""` | Prepended to every canonical URL as `f"{url_prefix}/{canonical_url}"`. A site served at the root uses `""`; mathnotes uses `"/mathnotes"`. A trailing slash is normalized away at `configure()` time. |
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

Load `latexblocks.css` BEFORE the site theme so the site's `:root` values
win over the bundle's own defaults.

At runtime the bundle wires up two features:

- **Reference tooltips**: hover/tap targets matching
  `a.block-reference, .notation-ref[data-ref-label]` (the second half covers
  notation refs stamped onto MathML elements, where `<a>` isn't legal, so
  those need JS-driven navigation via `data-ref-url` instead of `href`).
  Tooltip content comes from a JSON island the page must emit:
  `<script type="application/json" id="tooltip-data">[...]</script>`, an
  **array** of objects each carrying `label`, `type`, `title`, `content`,
  and optionally `url`, `is_synonym`, `synonym_of`, `synonym_title`.

  `render_page()["tooltip_data"]` is a **dict** keyed by label, and its
  entry values do NOT contain a `label` key — so the page must fold the key
  into each entry before serializing. Use exactly this idiom:

  ```python
  import json
  island = json.dumps([
      {"label": label, **entry}
      for label, entry in sorted(result["tooltip_data"].items())
  ])
  ```

  (Planned: `get_tooltip_data()` may return the array shape directly in
  v0.2.0; until then the caller performs this transform.)
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

Both marker sections must currently contain at least one macro each — an
empty PRE-EXPANSION MACROS or MATH MACROS section is a hard build error.
(Planned: this constraint relaxes to allow empty sections in v0.2.0.)

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
./dev.sh pytest -q
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

The library code is MIT. The one exception is the bundled Latin Modern Math
webfont (`assets/fonts/LatinModernMath-Regular.woff2`), which is licensed
under the GUST Font License — its license text ships alongside it in
`assets/fonts/GUST-FONT-LICENSE.txt`.

Install latexblocks **unpacked** (a regular `pip install`, not a zipapp/pex
or any zip-imported form): the library resolves its packaged assets as real
filesystem paths to hand to `node` and `shutil`, which cannot read inside a
zip.

## Consumers

- **mathnotes** (lacunary.org): the static-site generator this library was
  extracted from; supplies `ContentDiscovery` as its `UrlMapper` and
  `url_prefix="/mathnotes"`.
- **imagining-syntax**: renders a glossary/definitions page from
  latexblocks content at Docker build time, in a build stage only — its
  runtime image never imports latexblocks or installs node.
