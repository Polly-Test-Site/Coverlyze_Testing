from __future__ import annotations

import json
from flask import current_app

AGENT_INSTRUCTION_PROMPT = r"""
CRITICAL FORMATTING RULE: Always use HTML tags for emphasis in your responses:
- Use <strong>text</strong> for bold (NEVER use **text**)
- Use <em>text</em> for italic (NEVER use *text*)
- Use proper HTML formatting throughout

You are an insurance agent who can quote and write personal lines policies.
Be concise. Ask only one question per turn.
"""

PHRASING_SYSTEM_BASE = (
    "You are Polly, a friendly insurance assistant. "
    "Output ONE short message (1–2 sentences). "
    "If the user is in an 'umbrella quote' flow, do not change topics or add extra questions. "
    "Ask only the next required question."
)


def with_instruction(*sections: str) -> str:
    return AGENT_INSTRUCTION_PROMPT + "\n\n" + "\n".join(s for s in sections if s)


def convert_markdown_to_html(text: str) -> str:
    import re
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text or "")
    text = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<em>\1</em>', text)
    return text


def llm_phrase(system_instructions: str, user_prompt: str) -> str:
    client = current_app.config["OPENAI_CLIENT"]
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": with_instruction(PHRASING_SYSTEM_BASE, system_instructions)},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=200,
            temperature=0.3,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return user_prompt


def build_messages(user_message, session_obj, user_profile, retrieved_context, flow_state,
                   allow_pretraining_fallback: bool = False, state_norm: str | None = None,
                   target_cov: str | None = None):
    system_base = with_instruction(
        "You are Polly, a helpful insurance assistant.",
        "Use light HTML (<h4>, <ul><li>, <table>, <strong>, <em>).",
        "NEVER use markdown asterisks (**) - always use HTML tags.",
        "Do not provide binding quotes; final premiums depend on carriers."
    )

    if allow_pretraining_fallback and state_norm:
        grounding_rules = (
            "RAG-GROUNDING:\n"
            "• Use 'RETRIEVED GUIDELINES' as the authoritative source when available.\n"
            "• If the retrieved text does not contain the requested fact for the specified state, "
            "you MAY use your general knowledge as a fallback, but you MUST:\n"
            f" – Limit the fallback strictly to the state: {state_norm}.\n"
            " – State that this is a best-effort fallback and may be outdated.\n"
            " – Prompt the user to confirm or provide a declarations page for verification.\n"
            "• If pretraining conflicts with retrieved text, DEFER to the retrieved text.\n"
            "• Never invent precise numbers without saying they are estimates if coming from fallback."
        )
    else:
        grounding_rules = (
            "RAG-GROUNDING:\n"
            "• The content under 'RETRIEVED GUIDELINES' is the ONLY authoritative source for state rules/limits.\n"
            "• If pretraining/your memory conflicts with it, DEFER to the retrieved text.\n"
            "• If the retrieved text lacks the requested fact, say: "
            "'<em>I don’t see that specific item in the current state guidelines.</em>' "
            "and offer next steps. Do NOT guess values."
        )

    profile_block = (
        f"USER PROFILE:\n"
        f"- Name: {user_profile.get('name','')}\n"
        f"- State: {user_profile.get('state','')}\n"
        f"- Home owned: {user_profile.get('home_owned')}\n"
        f"- Asset band: {user_profile.get('asset_band')}\n"
        f"- Tone: {user_profile.get('preferred_tone','')}\n"
    )

    doc_block = "DECLARATIONS CONTEXT (if present):\n" + f"- Structured: {json.dumps(session_obj.get('extracted_data', {}))[:2000]}\n"

    rag_block = "RETRIEVED GUIDELINES (authoritative):\n" + "\n".join([f"- {c[:300]}" for c in (retrieved_context or [])]) if retrieved_context else "RETRIEVED GUIDELINES: <none>"

    messages = [
        {"role": "system", "content": system_base + "\n" + grounding_rules},
        {"role": "system", "content": "BEHAVIOR RULES:\n1) One question per turn.\n2) Stay in active flow if any.\n3) Use specific policy details when advising.\n4) If unsure, ask a short clarifying question."},
        {"role": "system", "content": profile_block},
        {"role": "system", "content": doc_block},
        {"role": "system", "content": rag_block},
        {"role": "system", "content": f"RUNNING SUMMARY:\n{(session_obj.get('running_summary','') or '')[:2000]}"},
        {"role": "user", "content": user_message},
    ]
    return messages
