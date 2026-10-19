import os
import json
import socket
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

LLM_URL = os.environ.get(
    'LLM_URL',
    'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
)
LLM_MODEL = os.environ.get('LLM_MODEL', 'gemini-3.5-flash-lite')
CHUNK_CHARS = int(os.environ.get('CHUNK_CHARS', '120000'))
DEADLINE_S = 270
MAX_ATTEMPTS = 6

NOTES_PROMPT = """Analyze the YouTube transcript below and generate NoteGPT-style notes.

Use exactly these markdown sections, each as a '## ' heading starting with an emoji:
## 📋 Overview: Brief summary of the video.
## 💡 Key Takeaways: Main ideas and lessons.
## 📝 Detailed Notes: Organized '###' subheadings (each with a fitting emoji), short bullet points, and clear explanations.
## 🔑 Key Concepts: Important terms and definitions, with **bold** terms.
## 📌 Examples: Relevant examples, facts, and case studies from the transcript.
## ⚡ Actionable Insights: Practical steps and advice.
## ⏱ Timestamps: Important sections with [mm:ss] if available.
## 🏁 Final Summary: Most important points to remember.

Readability: short bullets (one idea each), **bold** key terms and numbers, a few relevant emojis on bullets, blank lines between sections. No walls of text.

Keep the notes clear, structured, informative, and easy to review. Remove filler and repetition, but preserve important details. Do not invent facts or add information not present in the transcript.
Write the notes in English. The transcript may be in any other language; translate it as needed.

YouTube Transcript: {transcript}"""

EXTRACT_PROMPT = """Part of a YouTube video transcript (possibly another language). Extract every important point, concept, definition, example, fact, number and piece of advice in English as compact bullets. No filler, do not invent facts.

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
        token = (body.get('token') or '').strip()

        if not transcript:
            return self._send(400, {'error': 'Transcript is required'})
        if not token:
            return self._send(400, {'error': 'API token is required'})

        try:
            result = summarize(transcript, token)
            return self._send(200, {'summary': result})
        except PermissionError as e:
            return self._send(401, {'error': str(e)})
        except TimeoutError as e:
            return self._send(504, {'error': str(e)})
        except Exception as e:
            return self._send(502, {'error': f'LLM upstream error: {str(e)}'})