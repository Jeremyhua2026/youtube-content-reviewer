import json
import os
import re

from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash"


class LLMError(Exception):
    pass


def _client() -> genai.Client:
    key = os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise LLMError("GOOGLE_API_KEY is not set.")
    return genai.Client(api_key=key)


LENGTH_GUIDANCE = {
    "tight": (
        "TARGET LENGTH: ~120-160 words across the WHOLE delivery_script combined. "
        "Each section should be ~20-30 words. The script should sound like one continuous, "
        "slightly breathless thought a person would say out loud — casual, a little rambly, "
        "with sections that flow directly into each other (no headers, no recap, no formal "
        "transitions). Think 'voice memo to a friend,' not 'TED talk.' Use contractions, "
        "natural filler ('basically,' 'I mean,' 'you know'), and short sentences."
    ),
    "normal": (
        "TARGET LENGTH: ~220-280 words across the WHOLE delivery_script. "
        "Each section ~40-60 words. Conversational and human, but more polished than a voice memo."
    ),
    "detailed": (
        "TARGET LENGTH: ~380-450 words across the WHOLE delivery_script. "
        "Each section ~70-95 words. Develop the ideas more fully but still natural and speakable."
    ),
}


SYSTEM_PROMPT = """You are an analyst who helps a specific person reflect on YouTube videos and prepare to share the ideas with others (the user typically posts a clip with the video's thumbnail visible, so the audience already knows a YouTube video is being referenced).

You will receive:
1. The YouTube video's title and creator (channel name).
2. The full transcript.
3. A free-form block of text describing the user's personal context (could be copy from their personal website, bio, notes about their goals, work, values, relationships, etc.). Read it carefully and pull out concrete details.

You must return a single JSON object — no prose outside the JSON — with EXACTLY these keys:

{
  "summary": "string — concise overview of what the video is about (2-4 sentences). The summary must work as standalone audio narration.",
  "creator_notes": "string — 1-2 sentences naming the creator and giving brief context about who they are or the kind of content they make. If you genuinely don't recognize the channel, infer their angle from the transcript style (e.g., 'a finance educator who breaks down personal money topics in a casual tone'). Never fabricate biographical facts.",
  "suggested_tags": "array of 3-5 short, lowercase, single or two-word topic tags (e.g., 'finance', 'productivity', 'personal-growth', 'money-mindset'). Used for library filtering. No spaces — use hyphens for multi-word tags.",
  "suggested_tags": ["string", "string", "..."],
  "key_insights": ["string", "string", "..."],
  "personal_relevance": "string — 2-4 sentences on how the video connects to the user's specific life context. Reference concrete details from their context.",
  "delivery_script": {
    "hook": "string — open with a relatable question or bold statement drawn from the video. The script is spoken over a clip where the YouTube thumbnail is visible, so it should feel like the user is reacting to a video they just watched. Phrases like 'I recently saw this video where...', 'There's this video that...', 'Just watched this and...' work well. You can also name the creator naturally if it adds credibility.",
    "context": "string — briefly set up why this topic matters right now.",
    "core_idea": "string — explain the main insight in plain conversational language.",
    "personal_tie": "string — weave in a detail from the user's life context to make it feel authentic. This part changes each time based on context.",
    "call_to_action": "string — close with a thought, question, or next step for the listener.",
    "note": "string — short note explaining which parts are fixed structure (hook, context, core_idea, call_to_action stay structurally consistent) vs. which parts the user should personalize further (especially personal_tie, plus any specific examples)."
  }
}

Tone for delivery_script: natural, human, conversational — like talking to a friend, not reading a report. The script should sound like the user reacting to a video they watched, since the audience sees the thumbnail. Keep each section flowing and speakable. Do not use markdown or bullet points inside the script sections.

CRITICAL: When the five script sections are spoken back-to-back, they must read as ONE continuous thought, not five separate paragraphs. The hook should bleed into the context which bleeds into the core idea, and so on. Do not restate ideas across sections. Do not use formal transitions ("Now let's talk about..." or "Moving on..."). The section labels are for the user's reference only — the audience never hears them. Strictly obey the SCRIPT LENGTH INSTRUCTION provided in the user message.

If the user's context is mostly empty, still produce the script but make personal_tie a generic placeholder and note that the user should fill in their context to personalize further.

Return ONLY the JSON object. No code fences, no commentary."""


def analyze(transcript: str, context, video_title: str = "", video_creator: str = "", length: str = "tight") -> dict:
    client = _client()

    if isinstance(context, dict):
        context_text = context.get("context", "") or json.dumps(context, indent=2)
    else:
        context_text = str(context or "")

    if not context_text.strip():
        context_text = "(The user has not provided personal context yet.)"

    meta_lines = []
    if video_title:
        meta_lines.append(f"Title: {video_title}")
    if video_creator:
        meta_lines.append(f"Creator / Channel: {video_creator}")
    meta_block = "\n".join(meta_lines) if meta_lines else "(unknown)"

    length_instr = LENGTH_GUIDANCE.get(length, LENGTH_GUIDANCE["tight"])

    user_message = (
        "VIDEO METADATA:\n"
        f"{meta_block}\n\n"
        "SCRIPT LENGTH INSTRUCTION:\n"
        f"{length_instr}\n\n"
        "PERSONAL CONTEXT:\n"
        f"{context_text}\n\n"
        "VIDEO TRANSCRIPT:\n"
        f"{transcript}"
    )

    try:
        resp = client.models.generate_content(
            model=MODEL,
            contents=user_message,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.7,
            ),
        )
    except Exception as e:
        raise LLMError(f"Gemini API call failed: {e}")

    text = (resp.text or "").strip()
    parsed = _extract_json(text)
    if parsed is None:
        raise LLMError("Gemini did not return valid JSON.")

    return _normalize(parsed)


def _extract_json(text: str):
    try:
        return json.loads(text)
    except Exception:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except Exception:
            pass
    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        try:
            return json.loads(brace.group(0))
        except Exception:
            pass
    return None


def _normalize(data: dict) -> dict:
    script = data.get("delivery_script") or {}
    if not isinstance(script, dict):
        script = {}
    return {
        "summary": str(data.get("summary", "")).strip(),
        "creator_notes": str(data.get("creator_notes", "")).strip(),
        "suggested_tags": [str(x).strip().lower().replace(" ", "-") for x in (data.get("suggested_tags") or []) if str(x).strip()],
        "key_insights": [str(x).strip() for x in (data.get("key_insights") or []) if str(x).strip()],
        "personal_relevance": str(data.get("personal_relevance", "")).strip(),
        "delivery_script": {
            "hook": str(script.get("hook", "")).strip(),
            "context": str(script.get("context", "")).strip(),
            "core_idea": str(script.get("core_idea", "")).strip(),
            "personal_tie": str(script.get("personal_tie", "")).strip(),
            "call_to_action": str(script.get("call_to_action", "")).strip(),
            "note": str(script.get("note", "")).strip(),
        },
    }
