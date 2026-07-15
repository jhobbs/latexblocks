// latexblocks browser bundle: reference tooltips + \@{label} copy affordance.
// Load with <script defer src=".../latexblocks.js"></script>; tooltip data
// comes from <script type="application/json" id="tooltip-data">.
import { initTooltipSystem } from './tooltip-system';
import { initLabelCopyToClipboard } from './label-copy';

function init(): void {
  initTooltipSystem();          // idempotent (module-level singleton guard)
  initLabelCopyToClipboard();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
