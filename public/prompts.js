// Gemini prompt templates, kept separate from gemini.js so the actual
// wording/instructions for the LLM can be tweaked without touching any
// request/retry/storage logic. Loaded as a plain global (same convention as
// the rest of this static site -- no bundler, so order of <script> tags
// matters: this file must load before gemini.js).
//
// Both templates use a literal "{transcript}" placeholder that gemini.js
// fills in with String.replace() -- keep exactly one occurrence per template.

const NOTES_PROMPT = `You are an exceptional teacher and expert learning-note writer.

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

## \u{1F4CB} At a Glance
In 2\u20134 sentences, explain what the video is about, its central message,
and what the reader will understand after reading the notes.
Do not preview every individual point.

## \u{1F9E0} The Explanation
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

## \u{1F511} Essential Concepts
List only the important technical terms, frameworks, or unfamiliar concepts
needed to understand the video.

Format: **Term** \u2014 short, plain-English definition.

Do not repeat explanations already provided in The Explanation.
If there are no meaningful technical terms, omit this section.

## \u{1F4CA} Comparisons & Reference Tables
Include a compact Markdown table ONLY if the transcript contains useful
comparisons, categories, stages, pros and cons, options, or numerical data
that are easier to scan in tabular form.

Choose relevant column headings and preserve important distinctions.
Do not duplicate the detailed explanation in the table.
If no table would genuinely help, omit this section.

## \u{1F3AF} Practical Application
Include actionable steps, techniques, or recommendations explicitly supported
by the video, when applicable.

Make each step concrete and explain its purpose briefly.
For procedural content, use a numbered sequence.
For general advice, use a short bullet list.
Do not manufacture action items for videos that are purely explanatory.

## \u23F1 Important Timestamps
Include only timestamps that are actually present or reliably identifiable
in the supplied transcript.

Use [mm:ss] for shorter videos and [hh:mm:ss] for longer videos.
Add a short label describing the topic at each timestamp.
Never invent or estimate timestamps. Omit this section if timestamps are unavailable.

## \u{1F3C1} Remember This
Finish with 3\u20135 short bullets containing the most important conclusions
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
{transcript}`;

const EXTRACT_PROMPT = `You are extracting useful information from one segment
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
{transcript}`;


const SHORT_SUMMARY_PROMPT = `You are an expert YouTube summarizer. Turn the supplied
transcript into a concise, accurate, easy-to-scan summary that lets viewers
understand the video's most important ideas without watching the entire video.

RULES:
- Identify the central message and the most valuable information.
- Preserve essential facts, figures, conclusions, and important caveats.
- Explain important ideas clearly; do not just list keywords.
- Remove filler, repetition, tangents, greetings, and unnecessary examples.
- Never invent information or introduce unsupported claims.
- Adapt the format to the content: tutorials should capture key steps,
  comparisons should preserve important differences, and discussions should
  capture the main arguments and insights.
- Avoid repeating information across sections.
- Use clear, natural English and concise Markdown.
- Aim for 60–120 words for a typical video. Use fewer for simple videos
  and more only when needed to preserve important information.
- Do not force a word count at the expense of accuracy.
- Do not include timestamps unless explicitly available and useful.

OUTPUT:
## Summary
Explain the video's central message in 1–2 sentences.

## Key Points
List 3–5 of the most important insights in concise bullets.
Omit this section if the video has only one or two meaningful points.

## Bottom Line
Give one short sentence stating the most important conclusion.
Omit this section if it would merely repeat the summary.

Return only the finished Markdown summary.

TRANSCRIPT:
{transcript}`;
