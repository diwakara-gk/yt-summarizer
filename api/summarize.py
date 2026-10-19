import os
import json
import socket
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler

# Gemini OpenAI-compatible endpoint & model ID
LLM_URL = os.environ.get(
    'LLM_URL',
    'https://generativelanguage.googleapis.com/v1beta/openai/chat/completions'
)
LLM_MODEL = os.environ.get('LLM_MODEL', 'gemini-3.8-flash')

# Gemini 3.8 Flash has a 1M token window and fast throughput, so most
# transcripts process in a single request without multi-step chunking.
CHUNK_CHARS = int(os.environ.get('CHUNK_CHARS', '120000'))
DEADLINE_S = 270    # Vercel maxDuration is 300s
MAX_ATTEMPTS = 6
_start = [0.0]


def llm(prompt, token):
    req = urllib.request.Request(
        LLM_URL,
        data=json.dumps({
            'model': LLM_MODEL,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.3,
        }).encode(),
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
            'User-Agent': 'transcript-summarizer/1.0',
        },
    )
    for attempt in range(MAX_ATTEMPTS):
        if time.time() - _start[0] > DEADLINE_S:
            raise RuntimeError('Time limit reached; try a shorter transcript')
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())['choices'][0]['message']['content'].strip()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise RuntimeError('Invalid or unauthorized API token')
            if e.code not in (429, 500, 502, 503, 504) or attempt == MAX_ATTEMPTS - 1:
                raise
            wait = float(e.headers.get('retry-after') or 5)
        except (urllib.error.URLError, socket.timeout):
            if attempt == MAX_ATTEMPTS - 1:
                raise
            wait = 3
        time.sleep(min(wait, 20))


NOTES_PROMPT = """Analyze the YouTube transcript below and generate NoteGPT-style notes.

Use exactly these markdown sections, each as a '## ' heading starting with an emoji:
##  Overview: Brief summary of the video.
##  Key Takeaways: Main ideas and lessons.
##  Detailed Notes: Organized '###' subheadings (each with a fitting emoji), short bullet points, and clear explanations.
##  Key Concepts: Important terms and definitions, with **bold** terms.
##  Examples: Relevant examples, facts, and case studies from the transcript.
##  Actionable Insights: Practical steps and advice.
## ⏱ Timestamps: Important sections with [mm:ss] if available.
##  Final Summary: Most important points to remember.

Readability: short bullets (one idea each), **bold** key terms and numbers, a few relevant emojis on bullets, blank lines between sections. No walls of text.

Keep the notes clear, structured, informative, and easy to review. Remove filler and repetition, but preserve important details. Do not invent facts or add information not present in the transcript.
Write the notes in English. The transcript may be in any other language; translate it as needed.

YouTube Transcript: {transcript}"""

EXTRACT_PROMPT = """Part of a YouTube video transcript (possibly another language). Extract every important point, concept, definition, example, fact, number and piece of advice in English as compact bullets. No filler, do not invent facts.

{transcript}"""


def summarize(text, token):
    _start[0] = time.time()
    if len(text) <= CHUNK_CHARS:
        return llm(NOTES_PROMPT.format(transcript=text), token)
    chunks = [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)]
    points = [llm(EXTRACT_PROMPT.format(transcript=c), token) for c in chunks]
    return llm(NOTES_PROMPT.format(transcript='\n'.join(points)).replace(
        'YouTube Transcript:', 'Extracted points from the transcript (English):'), token)


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            n = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(n) or b'{}')
        except Exception:
            return self._send(400, {'error': 'Invalid JSON body'})

        transcript = (body.get('transcript') or '').strip()
        token = (body.get('token') or '').strip()
        if not transcript:
            return self._send(400, {'error': 'Transcript is required'})
        if not token:
            return self._send(400, {'error': 'API token is required'})

        try:
            return self._send(200, {'summary': summarize(transcript, token)})
        except Exception as e:
            return self._send(502, {'error': f'LLM error: {e}'})
