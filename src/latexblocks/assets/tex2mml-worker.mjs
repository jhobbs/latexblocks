// Build-time LaTeX -> MathML worker. JSON-lines protocol on stdin/stdout:
//   {"id": 1, "latex": "x^2", "display": false}
//   -> {"id": 1, "mathml": "<math ...>"}  or  {"id": 1, "error": "message"}
// A TeX parse error is a per-request error response, never a crash;
// malformed protocol input terminates the worker with a nonzero exit.
import { createInterface } from 'node:readline';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

// The worker lives inside an installed Python package, where no node_modules
// exists above it, so a bare `import mathjax` cannot resolve. The consumer's
// environment provides mathjax (^3.2.2); resolve it from argv[3] (see
// mathml.py / configure(node_modules_dir=...)) or from the process cwd.
const requireFrom = createRequire(
  path.join(process.argv[3] || process.cwd(), 'noop.js'));
const mathjax = requireFrom('mathjax');

// Math macros live in latex/mathnotes.sty (single source of truth, shared
// with pdflatex). Parse the marked section: simple one-line
// \newcommand/\renewcommand{\name}[n]{expansion} definitions only.
function parseStyMacros(sty) {
  const macros = {};
  const begin = sty.indexOf('% BEGIN MATH MACROS');
  const end = sty.indexOf('% END MATH MACROS');
  if (begin === -1 || end === -1 || end <= begin) {
    throw new Error(`${styPath}: MATH MACROS markers not found`);
  }
  const section = sty.slice(begin, end);
  const definition = /\\(?:re)?newcommand\{\\([A-Za-z]+)\}(?:\[(\d)\])?\{/g;
  let match;
  while ((match = definition.exec(section)) !== null) {
    // brace-count to the matching close of the expansion body
    let depth = 1;
    let i = definition.lastIndex;
    while (i < section.length && depth > 0) {
      if (section[i] === '\\') i += 1; // skip escaped char
      else if (section[i] === '{') depth += 1;
      else if (section[i] === '}') depth -= 1;
      i += 1;
    }
    const body = section.slice(definition.lastIndex, i - 1);
    const [name, nargs] = [match[1], match[2]];
    macros[name] = nargs ? [body, parseInt(nargs, 10)] : body;
    definition.lastIndex = i;
  }
  if (Object.keys(macros).length === 0) {
    throw new Error(`${styPath}: no macros parsed from MATH MACROS section`);
  }
  return macros;
}

// Usage: node tex2mml-worker.mjs <macros.sty> [node-modules-parent-dir]
const styPath = process.argv[2];
if (!styPath) {
  process.stderr.write(
    'tex2mml-worker: usage: node tex2mml-worker.mjs <macros.sty> [node-modules-parent]\n');
  process.exit(1);
}

const MathJax = await mathjax.init({
  loader: { load: ['input/tex', '[tex]/cancel', '[tex]/html'] },
  tex: {
    // input/tex bundles base+ams+newcommand+autoload. noundefined would
    // render undefined macros as red text instead of erroring; drop it so
    // every bad expression is a loud build failure. cancel and html are
    // eagerly loaded here because the synchronous tex2mml API cannot service
    // autoload's async retry mechanism (html provides \class, which
    // render_math uses to tag notation references).
    packages: { '[-]': ['noundefined'], '[+]': ['cancel', 'html'] },
    macros: parseStyMacros(readFileSync(styPath, 'utf8')),
    formatError: (_jax, err) => { throw err; },
  },
});

// Some <mo>s get the wrong space from the browser's operator dictionary:
// named operators (\inf, \sup, \lim, \max, ...) aren't in it and get a thick
// space each side, so `\inf\{` renders with a gap; a bare | or / in the
// middle of an expression is spaced as an infix operator, so |A| = 0 renders
// as "|A |  =". For these "respaced" operators, set lspace/rspace to TeX's
// inter-atom spacing (MathJax's texSpacing() over the TeX classes) instead.
// Each gap between siblings gets one owner: a respaced operator on its
// right (as lspace), else one on its left (as rspace); a gap next to any
// other mo is left to that mo's dictionary spacing. A \left...\right group
// counts as an opening delimiter after a named operator, flush like \{.
const STATE = MathJax._.core.MathItem.STATE;
const { TEXCLASS } = MathJax._.core.MmlTree.MmlNode;
const SPACE_EM = {
  '': '0', thinmathspace: '0.1667em', mediummathspace: '0.2222em',
  thickmathspace: '0.2778em',
};

function isNamedOperator(mo) {
  return mo.isKind('mo') && mo.texClass === TEXCLASS.OP
    && /^[A-Za-z][A-Za-z\s]*$/.test(mo.getText());
}

function isRespaced(node) {
  if (!node?.isEmbellished) return false;
  const mo = node.coreMO();
  if (!mo.isKind('mo')) return false;
  return isNamedOperator(mo)
    || (['|', '/'].includes(mo.getText())
        && ![TEXCLASS.REL, TEXCLASS.BIN].includes(mo.texClass));
}

function opensWithFence(node) {
  return node.texClass === TEXCLASS.INNER
    && node.childNodes[0]?.texClass === TEXCLASS.OPEN;
}

// TeX space before `right`, or 0 when a dictionary-spaced mo sits on the
// other side of the gap and supplies it
function gapSpace(left, right) {
  if (!left || !right) return '0';
  if ((left.isEmbellished && !isRespaced(left))
      || (right.isEmbellished && !isRespaced(right))) return '0';
  if (isNamedOperator(left.coreMO?.() ?? left) && opensWithFence(right)) return '0';
  return SPACE_EM[right.texSpacing()];
}

function setOperatorSpacing(node) {
  for (const child of node.childNodes || []) {
    if (child && !child.isToken) setOperatorSpacing(child);
  }
  if (!node.isInferred && !node.isKind('mrow') && !node.isKind('math')) return;
  const kids = node.childNodes;
  kids.forEach((kid, i) => {
    if (!isRespaced(kid)) return;
    const prev = kids[i - 1];
    const next = kids[i + 1];
    const lspace = gapSpace(prev, kid);
    const rspace = isRespaced(next) ? '0' : gapSpace(kid, next);
    kid.coreMO().attributes.set('lspace', lspace);
    kid.coreMO().attributes.set('rspace', rspace);
  });
}

function tex2mml(latex, display) {
  const root = MathJax.startup.document.convert(
    latex, { display, end: STATE.CONVERT });
  root.setTeXclass(null);
  setOperatorSpacing(root);
  return MathJax.startup.toMML(root);
}

function escapeAttr(s) {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// MathJax emits two elements that were dropped from MathML Core, which is
// all Chrome/Safari implement. Rewrite them to Core-safe markup styled by
// styles/math.css:
//  - \tag{...} -> mlabeledtr: becomes a plain mtr with the label cell moved
//    last (class="math-tag", table gets class="math-tagged"; CSS pins the
//    label right, matching client MathJax's old tagSide default).
//  - \cancel{...} -> menclose notation="updiagonalstrike": becomes an mrow
//    with class="mml-cancel" (CSS draws the diagonal strike).
function toMathMLCore(mml) {
  if (mml.includes('<mlabeledtr>')) {
    mml = mml.replace(/<mtable([^>]*)><mlabeledtr>/g,
                      '<mtable$1 class="math-tagged"><mlabeledtr>');
    mml = mml.replace(
      /<mlabeledtr>(<mtd[^>]*>.*?<\/mtd>)(.*?)<\/mlabeledtr>/g,
      (_, label, rest) =>
        `<mtr>${rest}${label.replace('<mtd', '<mtd class="math-tag"')}</mtr>`);
  }
  // only updiagonalstrike menclose ever occurs (\cancel); leave any other
  // notation untouched rather than mis-pairing close tags
  if (mml.includes('<menclose notation="updiagonalstrike">')
      && !/<menclose notation="(?!updiagonalstrike")/.test(mml)) {
    mml = mml.replace(/<menclose notation="updiagonalstrike">/g,
                      '<mrow class="mml-cancel">');
    mml = mml.replace(/<\/menclose>/g, '</mrow>');
  }
  return mml;
}

const rl = createInterface({ input: process.stdin, terminal: false });
rl.on('line', (line) => {
  if (!line.trim()) return;
  let req;
  try {
    req = JSON.parse(line);
    if (typeof req.latex !== 'string' || typeof req.id !== 'number') {
      throw new Error('request must have numeric id and string latex');
    }
  } catch (e) {
    process.stderr.write(`tex2mml-worker: malformed request: ${e.message}\n`);
    process.exit(1);
  }
  let resp;
  try {
    let mml = tex2mml(req.latex, !!req.display);
    // single line: keeps page HTML compact and paragraph splitting inert
    mml = mml.replace(/\n\s*/g, '');
    mml = toMathMLCore(mml);
    // alttext override: render_math sends the \class-wrapped TeX as latex
    // but the author's original TeX as alttext (snippets and heading ids
    // derive from alttext and must not see the wrapper)
    mml = mml.replace('<math', `<math alttext="${escapeAttr(req.alttext ?? req.latex)}"`);
    resp = { id: req.id, mathml: mml };
  } catch (err) {
    resp = { id: req.id, error: String(err.message || err) };
  }
  process.stdout.write(JSON.stringify(resp) + '\n');
});
rl.on('close', () => process.exit(0));
