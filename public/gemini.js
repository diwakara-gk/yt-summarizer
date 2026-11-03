// Client-side replacement for the old api/key.py + api/summarize.py
// serverless functions. This is a fully static site now -- there is no
// server left to hide anything behind, so the Gemini key lives in
// localStorage instead of an HttpOnly cookie, and the LLM call goes
// straight from this browser to Google. Trade-off is explained to the
// user on settings.html: any script on the page can now read the key
// (the normal deal for "paste your own key, no backend" tools). Anyone
// wanting extra protection should restrict their key by HTTP referrer
// in Google Cloud Console.
//
// Prompt wording lives in prompts.js (YOUTUBE_SUMMARY_PROMPT / EXTRACT_PROMPT globals)
// -- load that file before this one. Keeping prompts out of this file means
// tweaking the LLM's instructions never risks touching the request/retry code.

const API_KEY_STORAGE_KEY = 'geminiApiKey';
const API_KEY_EXPIRY_STORAGE_KEY = 'geminiApiKeyExpiry';
const KEY_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 1 week
const MAX_KEY_LEN = 512;

function saveApiKey(rawToken) {
  const token = (rawToken || '').trim();
  if (!token) throw new Error('API key is required');
  if (token.length > MAX_KEY_LEN) throw new Error('That key looks too long to be valid');
  const expiresAt = Date.now() + KEY_TTL_MS;
  localStorage.setItem(API_KEY_STORAGE_KEY, token);
  localStorage.setItem(API_KEY_EXPIRY_STORAGE_KEY, String(expiresAt));
  return expiresAt;
}

function clearApiKey() {
  localStorage.removeItem(API_KEY_STORAGE_KEY);
  localStorage.removeItem(API_KEY_EXPIRY_STORAGE_KEY);
}

// Returns the saved key if present and not expired, else null -- and
// quietly sweeps up any expired leftovers so hasApiKey()/getApiKeyExpiry()
// never report a dead key as live.
function getApiKey() {
  const expiresAt = parseInt(localStorage.getItem(API_KEY_EXPIRY_STORAGE_KEY), 10);
  if (!Number.isFinite(expiresAt) || Date.now() > expiresAt) {
    clearApiKey();
    return null;
  }
  return localStorage.getItem(API_KEY_STORAGE_KEY) || null;
}

function hasApiKey() {
  return getApiKey() !== null;
}

// Epoch-ms the saved key expires at, or null if there isn't a live one.
function getApiKeyExpiry() {
  return getApiKey() === null ? null : parseInt(localStorage.getItem(API_KEY_EXPIRY_STORAGE_KEY), 10);
}

// ---- Gemini call logic, ported from api/summarize.py ----

const LLM_URL = 'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions';
const LLM_MODEL = 'gemini-3.5-flash-lite';
const CHUNK_CHARS = 120000;
const DEADLINE_MS = 10 * 60 * 1000; // generous: no serverless timeout to respect anymore
const MAX_ATTEMPTS = 6;

class PermissionErrorLLM extends Error {}
class TimeoutErrorLLM extends Error {}

// All prompt templates and TRANSCRIPT_BLOCK / EXTRACTED_BLOCK live in prompts.js.

// Maps a summary mode to a function returning its final write-up prompt.
// contentType (a NOTES_VARIANTS key) only matters for the two notes modes;
// unknown types fall back to 'general'. Add a new mode here, nowhere else
// (plus a button on the page that calls it).
const SUMMARY_MODES = {
  detailed: () => YOUTUBE_SUMMARY_PROMPT,
  short: () => YOUTUBE_SHORT_SUMMARY_PROMPT,
  notes: type => NOTES_PROMPTS[type] || NOTES_PROMPTS.general,
  shortNotes: type => SHORT_NOTES_PROMPTS[type] || SHORT_NOTES_PROMPTS.general,
};

// Inserts content at the template's {transcript} placeholder. Uses a function
// replacer on purpose: a plain string replacement would interpret "$&", "$'"
// etc. inside a transcript and silently mangle it.
function fillTranscript(template, content) {
  return template.replace('{transcript}', () => content);
}

async function sleepBounded(ms, deadlineMs) {
  const remaining = deadlineMs - Date.now();
  if (remaining <= 0) throw new TimeoutErrorLLM('Processing deadline exceeded during retry wait');
  await new Promise(resolve => setTimeout(resolve, Math.min(ms, 20000, remaining)));
}

async function callLLM(prompt, token, deadlineMs) {
  const body = JSON.stringify({
    model: LLM_MODEL,
    messages: [{ role: 'user', content: prompt }],
    temperature: 0.3,
  });

  for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt++) {
    if (Date.now() > deadlineMs) throw new TimeoutErrorLLM('Processing deadline exceeded');

    let res;
    try {
      res = await fetch(LLM_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        body,
      });
    } catch (networkErr) {
      // Covers offline, DNS failures, and CORS rejections alike.
      if (attempt === MAX_ATTEMPTS - 1) throw new Error(`Could not reach Gemini: ${networkErr.message}`);
      await sleepBounded(3000, deadlineMs);
      continue;
    }

    if (res.ok) {
      const data = await res.json();
      return (data.choices?.[0]?.message?.content || '').trim();
    }

    if (res.status === 401 || res.status === 403) {
      throw new PermissionErrorLLM('Invalid or unauthorized API key');
    }

    const retryable = [429, 500, 502, 503, 504].includes(res.status);
    if (!retryable || attempt === MAX_ATTEMPTS - 1) {
      let detail = '';
      try { detail = (await res.json())?.error?.message || ''; } catch (_) {}
      throw new Error(`LLM upstream error (${res.status})${detail ? ': ' + detail : ''}`);
    }

    const retryAfter = parseFloat(res.headers.get('retry-after'));
    await sleepBounded((Number.isFinite(retryAfter) ? retryAfter : 5) * 1000, deadlineMs);
  }
  throw new Error('Exceeded maximum retry attempts');
}

// mode picks the final write-up prompt (a SUMMARY_MODES key; 'detailed' is the default).
// onProgress(message) is optional and used to surface "chunk 2/4" style
// status text for long transcripts, since multiple round trips now happen
// straight from the browser instead of behind one server call.
async function summarizeTranscript(text, token, mode, onProgress, contentType) {
  const finalPrompt = (SUMMARY_MODES[mode] || SUMMARY_MODES.detailed)(contentType);
  const deadlineMs = Date.now() + DEADLINE_MS;

  if (text.length <= CHUNK_CHARS) {
    onProgress?.('Summarizing...');
    return callLLM(fillTranscript(finalPrompt, text), token, deadlineMs);
  }

  const chunks = [];
  for (let i = 0; i < text.length; i += CHUNK_CHARS) chunks.push(text.slice(i, i + CHUNK_CHARS));

  const points = [];
  for (let i = 0; i < chunks.length; i++) {
    onProgress?.(`Extracting key points (${i + 1}/${chunks.length})...`);
    points.push(await callLLM(fillTranscript(EXTRACT_PROMPT, chunks[i]), token, deadlineMs));
  }

  onProgress?.('Writing final notes...');
  const consolidatedPrompt = fillTranscript(finalPrompt.replace(TRANSCRIPT_BLOCK, () => EXTRACTED_BLOCK), points.join('\n'));
  return callLLM(consolidatedPrompt, token, deadlineMs);
}
