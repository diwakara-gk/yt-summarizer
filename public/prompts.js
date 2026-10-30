// Gemini prompt templates, kept separate from gemini.js so the actual
// wording/instructions for the LLM can be tweaked without touching any
// request/retry/storage logic. Loaded as a plain global (same convention as
// the rest of this static site -- no bundler, so order of <script> tags
// matters: this file must load before gemini.js).
//
// Both templates use a literal "{transcript}" placeholder that gemini.js
// fills in with String.replace() -- keep exactly one occurrence per template.

const NOTES_PROMPT = `Turn this YouTube transcript into clear, concise, detailed Markdown notes that teach the content well enough to understand without watching the video.

RULES:
- Write in simple, precise English; translate non-English content into English.
- Preserve important ideas, reasoning, examples, steps, facts, numbers, caveats, and limitations.
- Explain how and why concepts work when the transcript supports it.
- Remove filler and repetition, but never discard unique, useful information.
- Follow the video's logical flow; reorganize only for clarity.
- Do not invent details or silently replace the speaker's claims with outside knowledge.
- Use readable paragraphs, meaningful headings, concise bullets, and tables only when useful.
- Explain each idea fully once. Do not repeat it in definitions, tables, takeaways, or other sections.
- Omit sections that add no value. Keep notes as short as possible without losing essential understanding.

## 📋 At a Glance
Summarize the topic, main message, and learning outcome in 2–3 sentences.

## 🧠 The Explanation
Explain the main ideas under logical subheadings. Include essential reasoning, examples, procedures, and qualifications. This should be the main section.

## 🔑 Essential Concepts
Define important unfamiliar terms briefly. Do not repeat explanations above. Omit if unnecessary.

## 📊 Comparisons & Reference Tables
Include tables only for useful comparisons, categories, stages, or numerical reference data. Do not duplicate the main explanation. Omit if unnecessary.

## 🎯 Practical Application
Include source-supported steps or recommendations when relevant. Use numbered steps for procedures. Do not invent advice or repeat procedures already explained.

## ⏱️ Important Timestamps
Include only a few key moments with timestamps explicitly present in the transcript. Format as [mm:ss] — Topic or [hh:mm:ss] — Topic. Omit if unavailable.

TIMESTAMPS: Never put timestamps in headings, subheadings, paragraphs, bullets, or concept names. Use them only in Important Timestamps.

## 🏁 Remember This
End with 3–5 distinct, high-value facts or principles. Do not repeat earlier content.

FINAL CHECK: Preserve essential information, remove duplication, keep claims faithful to the transcript, and omit unnecessary sections. Return only the finished Markdown notes.

TRANSCRIPT:
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

// Used by notes-summarizer.html (mode "notes"). Transcript label: "TRANSCRIPT:".
const NOTES_SUMMARY_PROMPT = `You are an expert note-taker. Convert the YouTube transcript into clear, comprehensive Markdown notes that let readers understand the video without watching it.

## Instructions
- Begin the output with exactly one H1 line (# Title): a specific, descriptive title of 3–8 words, no quotes, no emoji, no trailing punctuation. Use no other H1 headings.
- Preserve all important concepts, explanations, examples, demonstrations, arguments, steps, warnings, limitations, and conclusions from the transcript.
- Remove filler and redundant statements, but never discard unique information.
- Rewrite spoken language into clear, natural English without changing the speaker's meaning.
- Explain technical concepts in simple language while retaining important details.
- Include timestamps in [HH:MM:SS] format when available.
- Do not invent facts, examples, statistics, quotes, timestamps, or sources.
- Attribute opinions and claims to the speaker. Preserve controversial or questionable statements faithfully without implying endorsement.

## Output Structure

### 1. At a Glance
Briefly state the topic, purpose, and main takeaway.

### 2. Detailed Notes
Organize the video's content under logical headings. Explain concepts, reasoning, examples, demonstrations, and procedures thoroughly enough that readers can learn without watching the video. Preserve important context and the speaker's sequence where useful.

### 3. Essential Concepts
Define important technical terms or ideas concisely. Avoid repeating explanations already given in Detailed Notes.

### 4. Examples and Reference Tables
Include useful examples, code, workflows, and comparison tables when supported by the transcript. Prefer tables for comparisons and numbered lists for ordered procedures. Do not duplicate content from other sections.

### 5. Practical Takeaways
List actionable steps, recommendations, prerequisites, and warnings mentioned in the video. Include this section only when relevant.

### 6. Fact Check / Claims to Verify
If external search or reliable sources are available, verify important factual claims and cite the sources. Otherwise, explicitly state that independent verification was not performed and list only claims that warrant checking. Never pretend to have verified a claim.

### 7. Key Things to Remember
End with 3–5 distinct, high-value revision points. Do not repeat the introduction or copy earlier explanations.

## Timestamp Rules
- Do not add timestamps to headings, subheadings, titles, bullet points, or concept names.
- For example, write "AWS CloudFormation Overview", NOT "AWS CloudFormation Overview [00:01:25]".
- Omit timestamps by default. Include one only when it is genuinely useful for locating a specific demonstration or important moment in the video.
- Never attach timestamps to every paragraph or section.

## Anti-Repetition Rules
- Explain each idea fully once, in its most appropriate section.
- Give every section a distinct purpose; cross-reference instead of repeating.
- Consolidate repeated explanations while retaining unique details and qualifications.
- Present comparisons in one table and procedures in one complete explanation, with a short checklist elsewhere only if useful.
- Every bullet must add new information or practical value.
- Do not force unnecessary sections or pad the notes.
- Prioritize completeness, accuracy, and clarity over length.

## Final Check
Ensure all important source information is preserved, explanations are clear, timestamps are supported, and no duplicate content or fabricated verification remains.

Return only the finished Markdown notes.

TRANSCRIPT:
{transcript}`;
