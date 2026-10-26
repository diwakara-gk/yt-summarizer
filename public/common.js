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

// Asks the server whether a Gemini key cookie is currently set. Because the
// cookie is HttpOnly, this is the only way JS can even ask the question --
// it can never see the key's value, only true/false.
// Returns true/false, or null if the check itself failed (e.g. offline),
// so callers can tell "no key" apart from "couldn't check."
async function fetchHasApiKey() {
  try {
    const r = await fetch('/api/key', { method: 'GET' });
    const d = await r.json();
    return !!d.hasKey;
  } catch {
    return null;
  }
}
