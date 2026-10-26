import os
import json
import socket
import time
import urllib.error
import urllib.request
from http import cookies
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote

# Inlined rather than imported from a shared helper module: Vercel's Python
# runtime bundles each api/*.py file as an isolated function, and relying
# on it to also pick up a sibling module turned out to crash in production
# (FUNCTION_INVOCATION_FAILED). A few duplicated lines here beat a broken
# deploy -- see api/key.py for the matching copy of this logic.
COOKIE_NAME = 'gemini_key'


def read_token_cookie(headers) -> str:
    raw = headers.get('Cookie')
    if not raw:
        return ''
    jar = cookies.SimpleCookie()
    try:
        jar.load(raw)
    except Exception:
        return ''
    morsel = jar.get(COOKIE_NAME)
    if not morsel:
        return ''
    try:
        return unquote(morsel.value)
    except Exception:
        return ''

LLM_URL = os.environ.get(
    'LLM_URL',
    'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
)
LLM_MODEL = os.environ.get('LLM_MODEL', 'gemini-3.5-flash-lite')
CHUNK_CHARS = int(os.environ.get('CHUNK_CHARS', '120000'))
DEADLINE_S = 270
MAX_ATTEMPTS = 6


NOTES_PROMPT = """You are an exceptional teacher and expert learning-note writer.

Your job is to turn the YouTube transcript below into clear, engaging,
high-value study notes that help the reader UNDERSTAND the video,
not merely reread what the speaker said.

CORE PRINCIPLE:
Explain every important idea well, in the right place, exactly once.
Prefer clarity and understanding over completeness and length.

WRITING RULES:
- Write in natural, simple, precise English. Translate other languages into English.
- Explain concepts as a great teacher would: what it means, how it works,
  why it matters, and how it connects to other ideas.
- Follow the video's logical flow, reorganizing only when it improves understanding.
- Remove filler, repetition, unnecessary storytelling, and redundant explanations.
- Never repeat an explanation across sections.
- Do not turn every sentence into a bullet. Group related ideas together.
- Use short paragraphs and concise bullets with enough explanation to be useful.
- Bold only genuinely important terms, conclusions, and numbers.
- Use emojis sparingly and only when they improve navigation.
- Use tables ONLY when they make comparisons, categories, processes,
  numbers, or alternatives easier to understand.
- Do not force information into tables when bullets or prose are clearer.
- Do not add generic advice, unrelated background knowledge, or invented details.
- Preserve important qualifications, limitations, disagreements, and nuances.
- If the transcript does not provide enough information, say so rather than guess.
- Aim for the shortest notes that preserve the video's essential understanding.
  Video length alone is not a reason to make notes excessively long.

OUTPUT FORMAT:

## 📋 At a Glance
In 2–4 sentences, explain what the video is about, its central message,
and what the reader will understand after reading the notes.
Do not preview every individual point.

## 🧠 The Explanation
This is the MAIN section and should contain most of the useful content.

Organize the explanation into meaningful ### subheadings with a relevant emoji.
Follow the video's natural progression or a clearer teaching sequence.

For each major idea:
- Explain the idea in plain English.
- Explain how or why it works when the transcript provides that information.
- Connect cause and effect, reasoning, or related concepts where relevant.
- Include essential supporting facts, evidence, numbers, and caveats.
- Use a brief example when it genuinely improves understanding.

Explain each idea fully in one place. Do not create separate paragraphs
that repeat the same point in different words.

Include minor details only when they are necessary to understand a major idea.
Combine closely related points rather than creating too many subheadings.

## 🔑 Essential Concepts
List only the important technical terms, frameworks, or unfamiliar concepts
needed to understand the video.

Format: **Term** — short, plain-English definition.

Do not repeat explanations already provided in The Explanation.
If there are no meaningful technical terms, omit this section.

## 📊 Comparisons & Reference Tables
Include a compact Markdown table ONLY if the transcript contains useful
comparisons, categories, stages, pros and cons, options, or numerical data
that are easier to scan in tabular form.

Choose relevant column headings and preserve important distinctions.
Do not duplicate the detailed explanation in the table.
If no table would genuinely help, omit this section.

## 🎯 Practical Application
Include actionable steps, techniques, or recommendations explicitly supported
by the video, when applicable.

Make each step concrete and explain its purpose briefly.
For procedural content, use a numbered sequence.
For general advice, use a short bullet list.
Do not manufacture action items for videos that are purely explanatory.

## ⏱ Important Timestamps
Include only timestamps that are actually present or reliably identifiable
in the supplied transcript.

Use [mm:ss] for shorter videos and [hh:mm:ss] for longer videos.
Add a short label describing the topic at each timestamp.
Never invent or estimate timestamps. Omit this section if timestamps are unavailable.

## 🏁 Remember This
Finish with 3–5 short bullets containing the most important conclusions
the reader should retain after reading the notes.

These bullets must be a compact memory aid, not another summary.
Do not repeat entire explanations, examples, tables, or lists of takeaways.

FINAL QUALITY CHECK BEFORE RESPONDING:
1. Is each idea explained in only one main location?
2. Does each paragraph add new information?
3. Have redundant takeaways and repeated conclusions been removed?
4. Can long bullet lists be combined into clearer groups?
5. Are the tables genuinely useful rather than decorative?
6. Is the result substantially easier to read than a transcript?
7. Have all claims remained faithful to the transcript?

If a sentence adds no new understanding, remove it.
If a section has no useful content, omit it.
Return only the finished Markdown notes.

YouTube Transcript:
{transcript}"""



EXTRACT_PROMPT = """You are extracting useful information from one segment
of a YouTube transcript to help create a single, coherent set of study notes.

Extract the information that is necessary to understand the video's main ideas.

RULES:
- Write in concise, natural English, translating if necessary.
- Preserve important explanations, reasoning, facts, numbers, definitions,
  examples, caveats, and practical advice.
- Prefer a clear explanation of an idea over several repetitive bullet points.
- Combine related statements into one meaningful bullet.
- Preserve cause-and-effect relationships and the speaker's reasoning.
- Retain distinctive examples or evidence when they add understanding.
- Preserve timestamps exactly when they are available.
- Avoid generic introductions, conclusions, filler, and repeated claims.
- Do not invent missing context, facts, timestamps, or explanations.
- Do not force every sentence into a separate bullet.
- Keep the extraction compact; prioritize substance over volume.
- This is an intermediate extraction, NOT the final notes.
  Do not create a multi-section summary or repeat the same takeaway
  in different forms.
- If an idea is incomplete because the transcript segment ends,
  preserve what is known without guessing how it concludes.

Return organized bullets grouped by topic when appropriate.
Include only information that adds meaningful value.

Transcript segment:
{transcript}"""



def _parse_retry_after(header_val, default=5.0):
    if not header_val:
        return default
    try:
        return float(header_val)
    except (ValueError, TypeError):
        return default


def llm(prompt: str, token: str, deadline: float) -> str:
    payload = json.dumps({
        'model': LLM_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.3,
    }).encode('utf-8')

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}',
        'User-Agent': 'transcript-summarizer/1.0',
    }

    for attempt in range(MAX_ATTEMPTS):
        if time.time() > deadline:
            raise TimeoutError('Processing deadline exceeded')

        req = urllib.request.Request(LLM_URL, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                res_data = json.loads(r.read().decode('utf-8'))
                return res_data['choices'][0]['message']['content'].strip()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise PermissionError('Invalid or unauthorized API token')
            if e.code not in (429, 500, 502, 503, 504) or attempt == MAX_ATTEMPTS - 1:
                raise
            wait = _parse_retry_after(e.headers.get('retry-after'), default=5.0)
        except (urllib.error.URLError, socket.timeout):
            if attempt == MAX_ATTEMPTS - 1:
                raise
            wait = 3.0

        # Back off, bounded to not sleep past the deadline
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError('Processing deadline exceeded during retry wait')
        time.sleep(min(wait, 20.0, remaining))

    raise RuntimeError('Exceeded maximum retry attempts')


def summarize(text: str, token: str) -> str:
    deadline = time.time() + DEADLINE_S

    if len(text) <= CHUNK_CHARS:
        return llm(NOTES_PROMPT.format(transcript=text), token, deadline)

    chunks = [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)]
    points = [llm(EXTRACT_PROMPT.format(transcript=c), token, deadline) for c in chunks]

    consolidated_prompt = NOTES_PROMPT.format(
        transcript='\n'.join(points)
    ).replace('YouTube Transcript:', 'Extracted points from the transcript (English):')

    return llm(consolidated_prompt, token, deadline)


class handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj: dict):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            content_len = int(self.headers.get('Content-Length', 0))
            if content_len <= 0 or content_len > 10 * 1024 * 1024:  # 10MB guard
                return self._send(400, {'error': 'Invalid or oversized payload'})
            body = json.loads(self.rfile.read(content_len).decode('utf-8'))
        except Exception:
            return self._send(400, {'error': 'Malformed JSON body'})

        transcript = (body.get('transcript') or '').strip()
        # Explicit body token wins (handy for curl/testing); otherwise fall
        # back to the HttpOnly session cookie set via /api/key.
        token = (body.get('token') or '').strip() or read_token_cookie(self.headers)

        if not transcript:
            return self._send(400, {'error': 'Transcript is required'})
        if not token:
            return self._send(400, {'error': 'No API key saved. Set one on the Manage Key page first.'})

        try:
            result = summarize(transcript, token)
            return self._send(200, {'summary': result})
        except PermissionError as e:
            return self._send(401, {'error': str(e)})
        except TimeoutError as e:
            return self._send(504, {'error': str(e)})
        except Exception as e:
            return self._send(502, {'error': f'LLM upstream error: {str(e)}'})