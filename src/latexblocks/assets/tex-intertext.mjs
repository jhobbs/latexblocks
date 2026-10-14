// \intertext{...} and \shortintertext{...} for MathJax 3's TeX input, with
// the semantics of amsmath / mathtools:
//   - allowed directly inside align*, gather*, alignat*, flalign* (and their
//     numbered forms); anywhere else (aligned, split, cases, a matrix, an
//     open group) is "Invalid use of \intertext", like amsmath's error
//   - usable right after \\ or mid-row (amsmath then ends the row itself:
//     \ifvmode\else\\\fi), and as the last thing in the environment
//   - the argument is prose plus $...$ / \(...\) inline math; newlines
//     collapse to spaces
//
// MathJax upstream declined this for a decade (mathjax/MathJax#736): MathML
// has no intertext construct and a centered mtable cannot put text at the
// margin. The row is emitted as part of the alignment's own mtable so the
// alignment survives the interruption; the layout (full-width table, flank
// columns that keep the equations centered, a wrapping HTML prose block)
// is done by layoutIntertext() + intertextCellsToHtml() below and the
// library stylesheet. See docs: mathnotes
// docs/superpowers/specs/2026-10-14-intertext-design.md.

const ALLOWED_ENVS = new Set([
  'align', 'align*', 'alignat', 'alignat*', 'flalign', 'flalign*',
  'gather', 'gather*', 'xalignat', 'xalignat*', 'xxalignat',
]);

// Register the TeX extension. Must run after the input/tex component has
// loaded and before the TeX input jax is created (startup.ready), and the
// jax must list 'intertext' in tex.packages.
export function registerIntertext(MathJax) {
  const tex = MathJax._.input.tex;
  const { Configuration } = tex.Configuration;
  const { CommandMap } = tex.SymbolMap;
  const TexError = tex.TexError.default;
  const ParseUtil = tex.ParseUtil.default;
  const NodeUtil = tex.NodeUtil.default;

  const isAlignment = (item) => item.isKind('eqnarray') || item.isKind('flalign');
  const invalid = (parser) => new TexError(
    'InvalidIntertext',
    'Invalid use of %1 (allowed only directly inside align*, gather*, alignat*, or flalign*)',
    parser.currentCS);

  function Intertext(parser, name, short = false) {
    if (!ALLOWED_ENVS.has(parser.tags.currentTag.env)) throw invalid(parser);
    let top = parser.stack.Top();
    if (!isAlignment(top) || top.Size() || top.row.length) {
      // Mid-row, possibly with pending items (a prime, a subscript) above
      // the alignment: end the row exactly as \\ does, by pushing the same
      // cell item, which resolves pending items on its way down the stack.
      try {
        parser.Push(parser.itemFactory.create('cell')
          .setProperties({ isCR: true, name: '\\\\' }));
      } catch (e) {
        throw invalid(parser);
      }
      top = parser.stack.Top();
      if (!isAlignment(top)) throw invalid(parser);
    }
    const text = proseSource(
      parser.GetArgument(name).replace(/\s+/g, ' ').trim(), parser, TexError);
    // Same text-with-math parsing as \text{}: mtext runs and TeXAtoms,
    // which internalMath wraps in one mrow when there are several
    let nodes = ParseUtil.internalMath(parser, text);
    if (nodes.length === 1 && nodes[0].isKind('mrow') && !nodes[0].isInferred) {
      nodes = [...nodes[0].childNodes];
    }
    for (const node of nodes) {
      if (!node.isKind('mtext')) continue;
      const t = node.childNodes[0];
      // internalText pads run boundaries with nbsp; the prose must be able
      // to wrap there. Then the text-mode escapes LaTeX needs in prose
      // (\& especially: a bare & is an alignment tab) and ~ as nbsp.
      // internalMath leaves any other control sequence as literal text;
      // this dialect errors instead of rendering "\emph{x}".
      const prose = t.getText().replace(/ /g, ' ')
        .replace(/\\([&%#_])/g, '$1').replace(/~/g, ' ');
      // proseSource() already rejected everything else; safety net
      const macro = prose.match(/\\[A-Za-z]+|\\[\s\S]?/);
      if (macro) throw invalidMacro(parser, TexError, macro[0]);
      t.setText(prose);
    }
    const mtd = parser.create('node', 'mtd', nodes);
    NodeUtil.setAttribute(mtd, 'columnalign', 'left');
    NodeUtil.setAttribute(mtd, 'class', short ? 'intertext intertext-short' : 'intertext');
    const mtr = parser.create('node', 'mtr', [mtd]);
    NodeUtil.setAttribute(mtr, 'class', 'intertext');
    mtr.setProperty('intertext', true);
    top.table.push(mtr);
  }

  new CommandMap('intertext-macros', {
    intertext: 'Intertext',
    shortintertext: ['Intertext', true],
  }, { Intertext });
  Configuration.create('intertext', { handler: { macro: ['intertext-macros'] } });
}

const PROSE_ESCAPES = '${}&%#_';

function invalidMacro(parser, TexError, name) {
  return new TexError('IntertextMacro',
    '%1 in %2 prose is unsupported (plain text, \\& \\%% \\# \\_ \\$ \\{ \\}, ~, and $...$ math only)',
    name, parser.currentCS);
}

// Validate the raw argument before internalMath sees it, so errors name
// what the author wrote, and return it with LaTeX's silent grouping braces
// removed from the text portions. Text portions may contain only plain
// text, the escapes \& \% \# \_ \$ \{ \}, and ~; $...$ / \(...\) math is
// copied through for internalMath. Anything else is an error, as pdflatex
// would error or render something else: other control sequences, \\,
// \ref / \eqref (internalMath would turn them into a ??? link), and the
// bare specials & # ^ _ % (an alignment tab, a parameter, scripts, a
// comment in TeX; internalMath would print them).
function proseSource(text, parser, TexError) {
  let out = '';
  let i = 0;
  while (i < text.length) {
    const c = text[i];
    if (c === '$') {
      let j = i + 1;
      while (j < text.length && text[j] !== '$') j += text[j] === '\\' ? 2 : 1;
      if (j >= text.length) { out += text.slice(i); break; }  // internalMath reports it
      out += text.slice(i, j + 1);
      i = j + 1;
      continue;
    }
    if (c === '\\') {
      const next = text[i + 1];
      if (next === '(') {
        const j = text.indexOf('\\)', i + 2);
        if (j === -1) { out += text.slice(i); break; }
        out += text.slice(i, j + 2);
        i = j + 2;
        continue;
      }
      if (next !== undefined && PROSE_ESCAPES.includes(next)) {
        out += c + next;
        i += 2;
        continue;
      }
      const word = text.slice(i).match(/^\\([A-Za-z]+)/);
      if (word) {
        // render_math rewrites a notation macro \NAME to
        // \class{notation-ref notation-ref--NAME}{...}; name the macro
        const notation = text.slice(i).match(/^\\class\{notation-ref notation-ref--([A-Za-z]+)\}/);
        throw invalidMacro(parser, TexError, '\\' + (notation ? notation[1] : word[1]));
      }
      throw invalidMacro(parser, TexError, next === undefined ? '\\' : '\\' + next);
    }
    if (c === '{' || c === '}') { i += 1; continue; }
    if ('&#^_%'.includes(c)) {
      throw new TexError('IntertextSpecial',
        'bare %1 in %2 prose: write \\%1 for the character, or $...$ for math',
        c, parser.currentCS);
    }
    out += c;
    i += 1;
  }
  return out;
}

// Post-pass on the MmlNode tree: every mtable with intertext rows becomes a
// full-width table whose equation rows get an empty flank cell at each end
// (CSS gives both 50%, which keeps the equation group centered whatever the
// prose width) and whose text rows span every column. Returns true if any
// table was changed, so the caller can mark the root <math>.
export function layoutIntertext(root) {
  let found = false;
  const visit = (node) => {
    if (node.isKind('mtable') && layoutTable(node)) found = true;
    for (const child of node.childNodes || []) {
      if (child && !child.isToken) visit(child);
    }
  };
  visit(root);
  return found;
}

function layoutTable(mtable) {
  const rows = mtable.childNodes;
  if (!rows.some((row) => row.getProperty('intertext'))) return false;
  const factory = mtable.factory;
  const flank = () => {
    const mtd = factory.create('mtd');
    mtd.attributes.set('class', 'intertext-flank');
    return mtd;
  };
  // mlabeledtr: the label is the first child and is not a column
  const equationCells = (row) => row.childNodes.length - (row.isKind('mlabeledtr') ? 1 : 0);
  const columns = Math.max(1, ...rows
    .filter((row) => !row.getProperty('intertext')).map(equationCells));
  for (const row of [...rows]) {
    if (row.getProperty('intertext')) {
      row.childNodes[0].attributes.set('columnspan', columns + 2);
      continue;
    }
    const cells = [...row.childNodes];
    const label = row.isKind('mlabeledtr') ? cells.shift() : null;
    // MathJax leaves short rows short (a row without &, a lone line); the
    // right flank must still land in the flank column, not an equation one
    while (cells.length < columns) cells.push(factory.create('mtd'));
    if (label) {
      // A \tag label becomes the right flank itself (right-aligned), not an
      // extra column: an auto column next to two 50% flanks would stick out
      // past the display by its own width in Gecko and Blink. mlabeledtr is
      // not MathML Core either, so the row becomes a plain mtr here (the
      // worker's own mlabeledtr rewrite then has nothing to do for it).
      label.attributes.set('class', 'intertext-flank math-tag');
      label.attributes.set('columnalign', 'right');
      const mtr = factory.create('mtr');
      mtr.setChildren([flank(), ...cells, label]);
      mtable.replaceChild(mtr, row);
      continue;
    }
    row.setChildren([flank(), ...cells, flank()]);
  }
  const attrs = mtable.attributes;
  // columnalign is per column (Firefox honors it); a per-gap columnspacing
  // list (alignat) needs an entry for each new gap
  // (attributes.get: EqnArray always sets both explicitly, but a value equal
  // to the MathML default is not reported by getExplicit)
  const columnalign = attrs.get('columnalign');
  if (columnalign) attrs.set('columnalign', `center ${columnalign} center`);
  // the flank gaps get 0em whether the value was one spacing for all gaps
  // (gather*: "1em", which Gecko would also apply to the new gaps) or a
  // per-gap list (alignat*)
  const spacing = String(attrs.get('columnspacing') ?? '').trim();
  const gaps = !spacing ? [] : /\s/.test(spacing) ? spacing.split(/\s+/) : Array(columns - 1).fill(spacing);
  attrs.set('columnspacing', ['0em', ...gaps, '0em'].join(' '));
  attrs.set('width', '100%');
  attrs.set('class', 'intertext');
  return true;
}

// Serialized-MathML pass: rewrite each intertext cell's children (mtext
// runs and inline-math atoms) into one mtext holding an HTML block --
// mtext is an HTML integration point, so the span is real HTML and the
// nested <math> elements are real MathML in every engine. No engine wraps
// mtext; an HTML block wraps (given a definite width by the stylesheet).
// The mpadded width="0" around it takes the prose out of the table's
// intrinsic width: Gecko sizes a cell from its MathML content's max-content
// width (the whole sentence on one line) whatever the block's own width,
// so without it the table grows to the sentence instead of wrapping it.
//   <mtd class="intertext" ...><mtext>so </mtext><mrow>...</mrow><mtext> then</mtext></mtd>
//   -> <mtd class="intertext" ...><mpadded width="0"><mtext><span class="intertext-text">so <math><mrow>...</mrow></math> then</span></mtext></mpadded></mtd>
const INTERTEXT_MTD = /<mtd\b[^>]*\bclass="intertext(?: intertext-short)?"[^>]*>/g;
const MTD_TAG = /<(\/?)mtd\b[^>]*>/g;
const ANY_TAG = /<(\/?)([A-Za-z][\w:-]*)\b[^>]*>/g;

export function intertextCellsToHtml(mml) {
  if (!mml.includes('class="intertext')) return mml;
  let out = '';
  let last = 0;
  INTERTEXT_MTD.lastIndex = 0;
  let open;
  while ((open = INTERTEXT_MTD.exec(mml)) !== null) {
    const start = open.index + open[0].length;
    const end = matchingClose(mml, start, MTD_TAG);
    out += mml.slice(last, open.index) + open[0]
      + '<mpadded width="0"><mtext><span class="intertext-text">'
      + topLevelChildren(mml.slice(start, end)).map(({ tag, markup }) =>
        tag === 'mtext'
          ? markup.replace(/^<mtext\b[^>]*>/, '').replace(/<\/mtext>$/, '')
          : `<math>${markup}</math>`).join('')
      + '</span></mtext></mpadded>';
    last = end;
    INTERTEXT_MTD.lastIndex = end;
  }
  return out + mml.slice(last);
}

// Index of the close tag that balances an element whose content starts at
// `from`; `tagRe` matches that element's open/close tags (group 1 = '/').
// Serializer output is well-formed, so depth counting is exact.
function matchingClose(mml, from, tagRe) {
  const re = new RegExp(tagRe.source, 'g');
  re.lastIndex = from;
  let depth = 1;
  let m;
  while ((m = re.exec(mml)) !== null) {
    depth += m[1] ? -1 : 1;
    if (depth === 0) return m.index;
  }
  throw new Error('intertext: unbalanced mtd in serialized MathML');
}

// Split well-formed markup into its top-level elements.
function topLevelChildren(markup) {
  const children = [];
  const re = new RegExp(ANY_TAG.source, 'g');
  let depth = 0;
  let start = 0;
  let tag = '';
  let m;
  while ((m = re.exec(markup)) !== null) {
    if (m[1]) {
      depth -= 1;
      if (depth === 0) children.push({ tag, markup: markup.slice(start, m.index + m[0].length) });
    } else {
      if (depth === 0) { start = m.index; tag = m[2]; }
      depth += 1;
    }
  }
  if (depth !== 0) throw new Error('intertext: unbalanced markup in intertext cell');
  return children;
}
