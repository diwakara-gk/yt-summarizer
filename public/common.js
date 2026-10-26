// Shared browser-side helpers used by every page's inline script.
// Plain globals on purpose: these are static files with no bundler/module
// loader, so a single <script src="common.js"> include is what keeps the
// `$` helper, status messages, and the "is a key saved?" check from being
// copy-pasted into every page that needs them.

const $ = id => document.getElementById(id);

// Sets the page's #status element text + styling.
// variant: 'error' -> red error box, 'ok' -> green confirmation box,
// omitted -> plain neutral text (e.g. "Summarizing...").
function setStatus(msg, variant) {
  const el = $('status');
  if (!el) return;
  el.className = variant === 'error' ? 'err' : variant === 'ok' ? 'ok' : '';
  el.textContent = msg || '';
}
