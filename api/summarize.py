import os
import json
import socket
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from youtube_transcript_api import YouTubeTranscriptApi

LLM_URL = os.environ.get('LLM_URL', 'https://api.groq.com/openai/v1/chat/completions')
LLM_MODEL = os.environ.get('LLM_MODEL', 'openai/gpt-oss-20b')
CHUNK_CHARS = 6000  # kept small: Telugu is token-heavy and Groq free tier is rate-limited
DEADLINE_S = 270    # Vercel maxDuration is 300s
MAX_ATTEMPTS = 6
_start = [0.0]


def extract_video_id(youtube_url):
    if not youtube_url.startswith(('http://', 'https://')):
        youtube_url = 'https://' + youtube_url
    p = urlparse(youtube_url)
    if p.hostname == 'youtu.be':
        return p.path[1:] or None
    if p.hostname in ('www.youtube.com', 'youtube.com', 'm.youtube.com'):
        if p.path == '/watch':
            q = parse_qs(p.query)
            return q['v'][0] if 'v' in q else None
        if p.path.startswith(('/embed/', '/v/', '/shorts/')):
            return p.path.split('/')[2]
    return None


def get_transcript(video_id):
    """Return (plain_text, timestamped_text)."""
    proxy = os.environ.get('PROXY_URL')
    if proxy:
        from youtube_transcript_api.proxies import GenericProxyConfig
        api = YouTubeTranscriptApi(proxy_config=GenericProxyConfig(http_url=proxy, https_url=proxy))
    else:
        api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)
    try:
        srt = transcript_list.find_transcript(['te'])
    except Exception:
        srt = transcript_list.find_transcript(['en', 'hi']).translate('te')
    snippets = list(srt.fetch())
    plain = " ".join(i.text.strip() for i in snippets)
    blocks, cur, start = [], [], 0
    for i in snippets:
        if not cur:
            start = int(i.start)
        cur.append(i.text.strip())
        if i.start - start >= 30:
            blocks.append(f"[{start // 60:02d}:{start % 60:02d}] " + " ".join(cur))
            cur = []
    if cur:
        blocks.append(f"[{start // 60:02d}:{start % 60:02d}] " + " ".join(cur))
    timed = "\n".join(blocks)
    return plain, timed


def llm(prompt):
    key = os.environ.get('GROQ_API_KEY')
    if not key:
        raise RuntimeError('GROQ_API_KEY is not configured on the server')
    req = urllib.request.Request(
        LLM_URL,
        data=json.dumps({
            'model': LLM_MODEL,
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.3,
        }).encode(),
        headers={'Content-Type': 'application/json',
                 'Authorization': f'Bearer {key}',
                 'User-Agent': 'transcript-summarizer/1.0'},
    )
    for attempt in range(MAX_ATTEMPTS):
        if time.time() - _start[0] > DEADLINE_S:
            raise RuntimeError('Time limit reached; try a shorter transcript')
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read())['choices'][0]['message']['content'].strip()
        except urllib.error.HTTPError as e:
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
## 📌 Overview: Brief summary of the video.
## 🎯 Key Takeaways: Main ideas and lessons.
## 📝 Detailed Notes: Organized '###' subheadings (each with a fitting emoji), short bullet points, and clear explanations.
## 🔑 Key Concepts: Important terms and definitions, with **bold** terms.
## 💡 Examples: Relevant examples, facts, and case studies from the transcript.
## ✅ Actionable Insights: Practical steps and advice.
## ⏱️ Timestamps: Important sections with [mm:ss] if available.
## 🏁 Final Summary: Most important points to remember.

Readability: short bullets (one idea each), **bold** key terms and numbers, a few relevant emojis on bullets, blank lines between sections. No walls of text.

Keep the notes clear, structured, informative, and easy to review. Remove filler and repetition, but preserve important details. Do not invent facts or add information not present in the transcript.
Write the notes in English. The transcript may be in Telugu or any other language; translate it as needed.

YouTube Transcript: {transcript}"""

COMBINE_PROMPT = """Below are notes generated from consecutive parts of one YouTube video transcript. Merge them into a single set of NoteGPT-style notes with these '## ' emoji-prefixed sections: 📌 Overview, 🎯 Key Takeaways, 📝 Detailed Notes, 🔑 Key Concepts, 💡 Examples, ✅ Actionable Insights, ⏱️ Timestamps, 🏁 Final Summary. Use short bullets, **bold** key terms, and a few relevant emojis. Remove repetition, keep important details and timestamps, and do not invent facts not present in the notes.

{parts}"""


EXTRACT_PROMPT = """Part of a YouTube video transcript (possibly Telugu or another language) with [mm:ss] timestamps. Extract every important point, concept, definition, example, fact, number and piece of advice in English as compact bullets. Keep the [mm:ss] timestamp beside each point. No filler, do not invent facts.

{transcript}"""


def summarize(text):
    _start[0] = time.time()
    if len(text) <= CHUNK_CHARS:
        return llm(NOTES_PROMPT.format(transcript=text))
    chunks = [text[i:i + CHUNK_CHARS] for i in range(0, len(text), CHUNK_CHARS)]
    points = [llm(EXTRACT_PROMPT.format(transcript=c)) for c in chunks]
    return llm(NOTES_PROMPT.format(transcript='\n'.join(points)).replace(
        'YouTube Transcript:', 'Extracted points from the transcript (English, with timestamps):'))


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
            url = body.get('url', '')
        except Exception:
            return self._send(400, {'error': 'Invalid JSON body'})
        pasted = (body.get('transcript') or '').strip()
        if pasted:
            transcript = timed = pasted
        else:
            vid = extract_video_id(url)
            if not vid:
                return self._send(400, {'error': 'Invalid YouTube URL'})
            try:
                transcript, timed = get_transcript(vid)
            except Exception as e:
                return self._send(502, {'error': f'Transcript error: {e}', 'blocked': True})
        try:
            return self._send(200, {'summary': summarize(timed), 'transcript': transcript})
        except Exception as e:
            return self._send(502, {'error': f'LLM error: {e}'})
