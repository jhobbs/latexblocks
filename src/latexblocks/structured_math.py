"""
Typed document model for Mathnotes

This module provides a system for parsing and rendering structured mathematical
content (theorems, definitions, proofs, etc.) with explicit boundaries and metadata.
"""

import html as html_lib
import re
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Tuple, Union, Iterator
from enum import Enum

# \x02<i>\x02 in body_html marks where children[i] renders inline
CHILD_MARKER_RE = re.compile("\x02(\\d+)\x02")
_DREF_TEXT_RE = re.compile(r'<a data-dref="([^"]+)">(.*?)</a>', re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_MATH_EL_RE = re.compile(r"<math\b[^>]*>.*?</math>", re.DOTALL)
_ALTTEXT_RE = re.compile(r'\balttext="([^"]*)"')
_INLINE_MATH_RE = re.compile(r"\$([^$]+)\$")

# Irregular noun plurals used by MathBlock.generate_plural and, reversed,
# by MathBlock.generate_singular.
_IRREGULAR_PLURALS = {
    'matrix': 'matrices',
    'vertex': 'vertices',
    'simplex': 'simplices',
    'vortex': 'vortices',
    'helix': 'helices',
    'index': 'indices',
    'axis': 'axes',
    'analysis': 'analyses',
    'basis': 'bases',
    'crisis': 'crises',
    'hypothesis': 'hypotheses',
    'parenthesis': 'parentheses',
    'thesis': 'theses',
    'formula': 'formulas',
    'datum': 'data',
    'criterion': 'criteria',
    'phenomenon': 'phenomena',
    'polyhedron': 'polyhedra',
    'automaton': 'automata',
    'radius': 'radii',
    'locus': 'loci',
    'focus': 'foci',
    'nucleus': 'nuclei',
    'syllabus': 'syllabi',
    'corpus': 'corpora',
    'genus': 'genera',
    # Mathematical terms
    'modulus': 'moduli',
    'torus': 'tori',
    'annulus': 'annuli',
    'calculus': 'calculi',
}
_IRREGULAR_SINGULARS = {v: k for k, v in _IRREGULAR_PLURALS.items()}
# Nouns that are their own plural; neither variant is generated.
_INVARIANT_NOUNS = {'series', 'species'}


def math_to_dollar_text(html_str: str) -> str:
    """Replace <math> elements with their $-delimited alttext TeX (display
    math gets $$), so snippet and heading-id derivation see the same text
    the $-delimiter era produced. No-op on HTML without <math> elements."""
    def repl(m):
        el = m.group(0)
        open_tag = el[: el.index(">") + 1]
        alt = _ALTTEXT_RE.search(open_tag)
        tex = html_lib.unescape(alt.group(1)) if alt else ""
        return f"$${tex}$$" if 'display="block"' in open_tag else f"${tex}$"
    return _MATH_EL_RE.sub(repl, html_str)


def body_text(html_str: str) -> str:
    """Snippet-grade plain text from emitted body HTML.

    Auto drefs (empty link text) flatten to their label with hyphens as
    spaces, mirroring how the old dialect flattened @refs in link text.
    """
    def flatten(m):
        inner = m.group(2)
        if inner.strip():
            return inner
        label = m.group(1).split(":", 1)[-1]
        return label.replace("-", " ")

    text = _DREF_TEXT_RE.sub(flatten, html_str)
    text = math_to_dollar_text(text)
    text = CHILD_MARKER_RE.sub(" ", text)
    text = _TAG_RE.sub("", text)
    text = html_lib.unescape(text)
    return " ".join(text.split())


def text_with_math_to_html(text: str) -> str:
    """HTML for plain text that may contain $...$ math: prose is escaped,
    complete math spans render through the math seam. Used for reference
    link text, block header titles, and tooltip title/type strings."""
    from .latex_processor import render_math  # local: latex_processor imports this module

    out = []
    pos = 0
    for m in _INLINE_MATH_RE.finditer(text):
        out.append(html_lib.escape(text[pos:m.start()], quote=False))
        out.append(render_math(m.group(1).strip(), display=False))
        pos = m.end()
    out.append(html_lib.escape(text[pos:], quote=False))
    return "".join(out)


def lowercase_outside_math(text: str) -> str:
    """Lowercase prose while leaving $...$ math spans untouched. Definition
    link text is lowercased for mid-sentence use; lowercasing TeX would
    change math meaning ($O$ -> $o$) or break macros (\\Log -> \\log)."""
    out = []
    pos = 0
    for m in _INLINE_MATH_RE.finditer(text):
        out.append(text[pos:m.start()].lower())
        out.append(m.group(0))
        pos = m.end()
    out.append(text[pos:].lower())
    return "".join(out)


def apply_reference_case(typed: str, title: str) -> Optional[str]:
    """Transfer the capitalization of a typed reference label onto a title:
    \\@{Set} renders "Set", \\@{set} renders "set". The title supplies the
    words, separators, and $...$ math spans (typed case never alters TeX);
    the typed label supplies only the letter case. Returns None when the
    typed label doesn't spell the title, so callers fall back to
    lowercase_outside_math."""
    segments = []
    pos = 0
    for m in _INLINE_MATH_RE.finditer(title):
        segments.append((title[pos:m.start()], True))
        segments.append((m.group(0), False))
        pos = m.end()
    segments.append((title[pos:], True))

    out = []
    ti = 0
    for seg, transfer in segments:
        for ch in seg:
            if not ch.isalnum():
                out.append(ch)
                continue
            while ti < len(typed) and not typed[ti].isalnum():
                ti += 1
            if ti >= len(typed) or typed[ti].lower() != ch.lower():
                return None
            out.append(typed[ti] if transfer else ch)
            ti += 1
    if any(c.isalnum() for c in typed[ti:]):
        return None
    return "".join(out)


class MathBlockType(Enum):
    """Types of mathematical content blocks."""

    DEFINITION = "definition"
    THEOREM = "theorem"
    LEMMA = "lemma"
    PROPOSITION = "proposition"
    COROLLARY = "corollary"
    AXIOM = "axiom"
    PROOF = "proof"
    EXAMPLE = "example"
    REMARK = "remark"
    NOTE = "note"
    INTUITION = "intuition"
    EXERCISE = "exercise"
    SOLUTION = "solution"
    EXPLANATION = "explanation"
    RESULT = "result"
    INTENT = "intent"
    BACKGROUND = "background"
    HYPOTHESIS = "hypothesis"
    CONCLUSION = "conclusion"
    VARIANT = "variant"
    CLAIM = "claim"


@dataclass
class DefinedTerm:
    """A further term defined inside a definition block via \\term{...}.

    The block's title is its primary term; each DefinedTerm is another
    concept the same block defines, with its own label (also the id of the
    term's <strong> in the body, so references land on the word itself),
    its own synonyms, and its own auto-generated plural/singular aliases.
    """

    title: str
    label: str
    synonyms: List[Tuple[str, str]] = field(default_factory=list)  # (synonym_title, synonym_label)
    auto_generated_synonyms: List[Tuple[str, str]] = field(default_factory=list)
    line: int = 0  # source line of the \\term, for collision errors


@dataclass
class MathBlock:
    """Represents a structured mathematical content block."""

    block_type: MathBlockType
    content: str  # plain text, inline math preserved
    title: Optional[str] = None
    label: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    children: List["MathBlock"] = field(default_factory=list)
    parent: Optional["MathBlock"] = None
    body_html: str = ""  # unresolved-placeholder HTML (child markers not yet substituted)
    content_html: Optional[str] = None  # Stores the inner HTML content (without wrapper)
    rendered_html: Optional[str] = None  # Fully rendered block HTML, once available
    synonyms: List[Tuple[str, str]] = field(default_factory=list)  # List of (synonym_title, synonym_label)
    auto_generated_synonyms: List[Tuple[str, str]] = field(default_factory=list)  # Auto-generated synonyms (not shown in UI)
    tags: List[str] = field(default_factory=list)  # List of tags for categorization
    notations: List[Tuple[str, str]] = field(default_factory=list)  # (macro name, TeX expansion)
    terms: List["DefinedTerm"] = field(default_factory=list)  # extra \\term{...}s a definition defines

    def walk(self) -> Iterator["MathBlock"]:
        yield self
        for child in self.children:
            yield from child.walk()

    @property
    def css_class(self) -> str:
        """Generate CSS class name for this block type."""
        return f"math-block math-{self.block_type.value}"

    @property
    def display_name(self) -> str:
        """Get the display name for this block type."""
        names = {
            MathBlockType.DEFINITION: "Definition",
            MathBlockType.THEOREM: "Theorem",
            MathBlockType.LEMMA: "Lemma",
            MathBlockType.PROPOSITION: "Proposition",
            MathBlockType.COROLLARY: "Corollary",
            MathBlockType.AXIOM: "Axiom",
            MathBlockType.PROOF: "Proof",
            MathBlockType.EXAMPLE: "Example",
            MathBlockType.REMARK: "Remark",
            MathBlockType.NOTE: "Note",
            MathBlockType.INTUITION: "Intuition",
            MathBlockType.EXERCISE: "Exercise",
            MathBlockType.SOLUTION: "Solution",
            MathBlockType.EXPLANATION: "Explanation",
        }
        return names.get(self.block_type, self.block_type.value.title())

    @property
    def content_snippet(self) -> str:
        """First 7 words of content, display math removed, for reference link text."""
        text = re.sub(r"\$\$.*?\$\$", "", self.content, flags=re.DOTALL)
        words = text.split()
        if not words:
            return self.label or "untitled"
        snippet = " ".join(words[:7])
        if len(words) > 7:
            snippet += "..."
        return snippet

    @staticmethod
    def normalize_label_from_title(title: str) -> str:
        """Generate a normalized label from a title."""
        import re

        # Convert to lowercase
        label = title.lower()

        # Replace whitespace, commas, and other punctuation with hyphens
        label = re.sub(r"[\s,]+", "-", label)

        # Remove any remaining non-alphanumeric characters except hyphens
        label = re.sub(r"[^a-z0-9-]", "", label)

        # Remove leading/trailing hyphens and collapse multiple hyphens
        label = re.sub(r"-+", "-", label).strip("-")

        return label

    @staticmethod
    def generate_plural(word: str) -> Optional[str]:
        """Generate the plural form of a word.

        Returns None if the word is already plural or if pluralization doesn't make sense.
        """
        if not word:
            return None

        # Skip if already plural (basic heuristic)
        if word.endswith('s') and not word.endswith('ss'):
            return None

        word_lower = word.lower()
        if word_lower in _INVARIANT_NOUNS:
            return None
        if word_lower in _IRREGULAR_PLURALS:
            # Preserve the original case
            if word[0].isupper():
                return _IRREGULAR_PLURALS[word_lower].capitalize()
            return _IRREGULAR_PLURALS[word_lower]

        # Regular plural rules
        if word.endswith('y'):
            # If preceded by a consonant, change y to ies
            if len(word) > 1 and word[-2] not in 'aeiou':
                return word[:-1] + 'ies'
            else:
                return word + 's'
        elif word.endswith(('s', 'ss', 'sh', 'ch', 'x', 'z', 'o')):
            return word + 'es'
        else:
            return word + 's'

    @staticmethod
    def generate_singular(name: str) -> Optional[str]:
        """Generate the singular form of a plural word or multi-word name
        (only the last word is singularized: "Real Numbers" -> "Real Number").

        Returns None if the name is not plural or is an invariant noun
        like "series".
        """
        if not name:
            return None

        head, sep, word = name.rpartition(' ')
        if sep:
            singular = MathBlock.generate_singular(word)
            return head + sep + singular if singular else None

        word_lower = word.lower()
        if word_lower in _INVARIANT_NOUNS:
            return None
        if word_lower in _IRREGULAR_SINGULARS:
            # Preserve the original case
            if word[0].isupper():
                return _IRREGULAR_SINGULARS[word_lower].capitalize()
            return _IRREGULAR_SINGULARS[word_lower]

        # Not plural (basic heuristic, mirroring generate_plural)
        if not word.endswith('s') or word.endswith('ss'):
            return None

        if word_lower.endswith('ies') and len(word) > 3:
            return word[:-3] + 'y'
        if word_lower.endswith(('sses', 'shes', 'ches', 'xes', 'zes', 'oes')):
            return word[:-2]
        return word[:-1]


@dataclass
class SectionLabel:
    """A \\label directly after a sectioning command: references to `label`
    land on the heading's id."""

    label: str
    title: str  # heading HTML
    heading_id: str
    line: int


@dataclass
class PageDoc:
    """Parsed page: prose HTML segments and top-level MathBlocks, in order,
    plus the page's labeled sections."""

    items: List[Union[str, MathBlock]] = field(default_factory=list)
    sections: List[SectionLabel] = field(default_factory=list)

    def top_blocks(self) -> List[MathBlock]:
        return [it for it in self.items if isinstance(it, MathBlock)]


_NESTED_AUTO_TYPES = {
    MathBlockType.NOTE, MathBlockType.EXAMPLE, MathBlockType.REMARK,
    MathBlockType.INTUITION, MathBlockType.EXERCISE, MathBlockType.SOLUTION,
}

# Types whose title, when no label is given, supplies the label.
_TITLE_LABELED_TYPES = {
    MathBlockType.DEFINITION, MathBlockType.THEOREM, MathBlockType.LEMMA,
    MathBlockType.PROPOSITION, MathBlockType.COROLLARY, MathBlockType.AXIOM,
}


def finalize_blocks(top_blocks: List[MathBlock]) -> None:
    """Assign auto labels, definition synonyms/plurals, and tags, in place."""
    counter = 0
    per_parent: Dict[Tuple[int, str], int] = {}

    def visit(block: MathBlock):
        nonlocal counter
        counter += 1
        if not block.label and block.block_type in _TITLE_LABELED_TYPES and block.title:
            block.label = MathBlock.normalize_label_from_title(block.title)
        if not block.label:
            parent = block.parent
            if block.block_type == MathBlockType.PROOF and parent and parent.label:
                key = (id(parent), "proof")
                per_parent[key] = per_parent.get(key, 0) + 1
                n = per_parent[key]
                block.label = f"proof-of-{parent.label}" + (f"-{n}" if n > 1 else "")
            elif parent and parent.label and block.block_type in _NESTED_AUTO_TYPES:
                key = (id(parent), block.block_type.value)
                per_parent[key] = per_parent.get(key, 0) + 1
                n = per_parent[key]
                block.label = f"{parent.label}-{block.block_type.value}" + (f"-{n}" if n > 1 else "")
            else:
                block.label = f"{block.block_type.value}-{counter}"
        # Untitled, unlabeled top-level theorem-likes auto-number via the
        # counter fallback above rather than erroring.
        if block.block_type == MathBlockType.DEFINITION:
            _build_definition_synonyms(block)
        if "tags" in block.metadata and not block.tags:
            block.tags = [
                t.strip().strip('"') for t in block.metadata["tags"].split(",") if t.strip()
            ]
        for child in block.children:
            visit(child)

    for b in top_blocks:
        visit(b)


def _build_definition_synonyms(block: MathBlock) -> None:
    _parse_manual_synonyms(block)
    # A \term naming the block's own title or one of its synonyms just marks
    # the primary term in the body: bold, but no separate entry and no id
    # (the card itself already carries that label). Its own synonyms join
    # the block's.
    primary = {block.label} | {lbl for _, lbl in block.synonyms}
    for term in [t for t in block.terms if t.label in primary]:
        block.terms.remove(term)
        for syn, lbl in term.synonyms:
            if lbl not in primary:
                primary.add(lbl)
                block.synonyms.append((syn, lbl))
        block.body_html = block.body_html.replace(
            f'<strong class="defined-term" id="{term.label}">',
            '<strong class="defined-term">', 1)

    seen_labels = {block.label}
    for term in block.terms:
        seen_labels.add(term.label)
        seen_labels.update(lbl for _, lbl in term.synonyms)
        seen_labels.update(lbl for _, lbl in term.auto_generated_synonyms)
    seen_labels.update(lbl for _, lbl in block.synonyms)
    seen_labels.update(lbl for _, lbl in block.auto_generated_synonyms)

    def add_auto(name: Optional[str]) -> None:
        if not name:
            return
        label = MathBlock.normalize_label_from_title(name)
        if label not in seen_labels:
            seen_labels.add(label)
            block.auto_generated_synonyms.append((name, label))

    names = [syn for syn, _ in block.synonyms]
    if block.title:
        names.append(block.title)
    for name in names:
        add_auto(MathBlock.generate_plural(name))
        add_auto(MathBlock.generate_singular(name))

    for term in block.terms:
        for name in [term.title] + [syn for syn, _ in term.synonyms]:
            for auto in (MathBlock.generate_plural(name), MathBlock.generate_singular(name)):
                if not auto:
                    continue
                label = MathBlock.normalize_label_from_title(auto)
                if label not in seen_labels:
                    seen_labels.add(label)
                    term.auto_generated_synonyms.append((auto, label))


def _parse_manual_synonyms(block: MathBlock) -> None:
    if "synonyms" in block.metadata and not block.synonyms:
        for syn in block.metadata["synonyms"].split(","):
            syn = syn.strip().strip('"')
            if syn:
                block.synonyms.append((syn, MathBlock.normalize_label_from_title(syn)))


def check_term_collisions(top_blocks: List[MathBlock]) -> List[Tuple[int, str]]:
    """Same-file \\term label collisions as (line, message), so a
    single-file parse reports them with a line number instead of leaving
    them to the whole-site index build. Cross-file collisions are still
    caught only there."""
    owners: Dict[str, str] = {}
    blocks = [b for t in top_blocks for b in t.walk()]
    for b in blocks:
        name = f"{b.block_type.value} '{b.title or b.label}'"
        owners.setdefault(b.label, name)
        for _, lbl in b.synonyms:
            owners.setdefault(lbl, f"a synonym of {name}")
    problems = []
    for b in blocks:
        for term in b.terms:
            for title, lbl in [(term.title, term.label)] + term.synonyms:
                if lbl in owners:
                    problems.append((term.line, f"\\term label '{lbl}' ({title}) "
                                     f"collides with {owners[lbl]} in this file"))
                else:
                    owners[lbl] = f"\\term '{term.title}'"
    return problems


def render_block_html(block: MathBlock, content_html: str, url: str) -> str:
    """Wrap resolved block content in the math-block card HTML."""
    css_classes = [block.css_class]
    if block.parent:
        css_classes.append("math-block-nested")
    attrs = [f'class="{" ".join(css_classes)}"',
             f'id="{block.label}"', f'data-label="{block.label}"']
    for key, value in block.metadata.items():
        if key != "label":
            attrs.append(f'data-{key}="{html_lib.escape(str(value))}"')

    parts = [f'<div {" ".join(attrs)}>', '<div class="math-block-header">']
    if block.block_type != MathBlockType.PROOF:
        if block.title:
            parts.append(f'<span class="math-block-type">{block.display_name}:</span>')
            parts.append(
                f'<span class="math-block-title"><a href="{url}">'
                f"{text_with_math_to_html(block.title)}</a></span>"
            )
        else:
            parts.append(f'<span class="math-block-type">{block.display_name}</span>')
    else:
        parts.append('<span class="math-block-type">Proof</span>')
    if block.synonyms:
        names = ", ".join(html_lib.escape(s[0]) for s in block.synonyms)
        parts.append(f'<span class="block-synonyms">(also: {names})</span>')
    if block.terms:
        names = ", ".join(text_with_math_to_html(t.title) for t in block.terms)
        parts.append(f'<span class="block-terms">(also defines: {names})</span>')
    if block.notations:
        from .latex_processor import render_math  # local: latex_processor imports this module

        rendered = ", ".join(
            render_math(expansion, display=False) for _, expansion in block.notations
        )
        parts.append(f'<span class="block-notation">Notation: {rendered}</span>')
    if block.tags:
        tags_html = "".join(
            f'<span class="block-tag">{html_lib.escape(t)}</span>' for t in block.tags
        )
        parts.append(f'<span class="block-tags">{tags_html}</span>')
    parts.append(f'<span class="block-label-ref">\\@{{{block.label}}}</span>')
    parts.append("</div>")

    marked = {int(i) for i in CHILD_MARKER_RE.findall(content_html)}

    def sub_child(m):
        child = block.children[int(m.group(1))]
        if child.rendered_html is None:
            raise ValueError(f"Child block '{child.label}' rendered out of order")
        return child.rendered_html

    processed = CHILD_MARKER_RE.sub(sub_child, content_html)
    for i, child in enumerate(block.children):
        if i not in marked:
            if child.rendered_html is None:
                raise ValueError(f"Child block '{child.label}' rendered out of order")
            processed += "\n" + child.rendered_html

    parts.append('<div class="math-block-content">')
    parts.append(processed)
    if block.block_type == MathBlockType.PROOF:
        from .latex_processor import render_math  # local: latex_processor imports this module

        qed = render_math("\\square", display=False)
        if not processed.rstrip().endswith(qed):
            parts.append(f" {qed}")
    parts.append("</div>")
    parts.append("</div>")
    return "\n".join(parts)
