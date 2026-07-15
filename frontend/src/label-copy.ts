// The \@{label} copy affordance: rewrites every .block-label-ref to the ※
// reference mark and copies the block's label to the clipboard on click.
// Extracted verbatim from mathnotes demos-framework/src/mathblock-toggle.ts;
// the statements-toggle in that file is mathnotes site policy and stays there.

export function initLabelCopyToClipboard(): void {
    const REFERENCE_MARK = '※';
    const COPY_SUCCESS = '✓';
    const COPY_FAILURE = '✗';
    const FEEDBACK_DURATION = 1500;

    // Add click handlers to all block reference labels
    const labels = document.querySelectorAll<HTMLElement>('.block-label-ref');
    labels.forEach(label => {
        // Store the original text as a data attribute
        const originalText = label.textContent || '';
        label.dataset.originalText = originalText;

        // Replace the text with the reference mark and add title for hover
        label.textContent = REFERENCE_MARK;
        label.title = originalText;

        // Add click handler
        label.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();

            // Don't allow clicks while showing feedback
            if (label.classList.contains('copied') || label.classList.contains('failed')) {
                return;
            }

            try {
                await navigator.clipboard.writeText(originalText);

                // Visual feedback via CSS class
                label.textContent = COPY_SUCCESS;
                label.classList.add('copied');

                setTimeout(() => {
                    label.textContent = REFERENCE_MARK;
                    label.classList.remove('copied');
                }, FEEDBACK_DURATION);
            } catch (err) {
                console.error('Failed to copy to clipboard:', err);

                // Fallback visual feedback via CSS class
                label.textContent = COPY_FAILURE;
                label.classList.add('failed');

                setTimeout(() => {
                    label.textContent = REFERENCE_MARK;
                    label.classList.remove('failed');
                }, FEEDBACK_DURATION);
            }
        });
    });
}
