from __future__ import annotations
import json
from datetime import timedelta
from typing import List, Optional

from flask import current_app


def search(query_text: str, *, state: Optional[str], top_k: int, line: str | None,
           topic: str | None, coverages_any: list[str] | None, section: str | None,
           allow_fallbacks: bool, strict_state: bool) -> list[dict]:
    """
    Thin wrapper around Qdrant search; implement your own payload schema.
    For now, we assume qdrant payload has fields: text, state, source, chunk_index, line, coverages, section
    """
    qc = current_app.config["QDRANT_CLIENT"]
    coll = current_app.config.get("QDRANT_COLLECTION", "state_guidelines")

    # Basic vector search via text-embedding-3-large
    from .embeddings import embed_texts
    vec = embed_texts([query_text])[0]

    # Optional payload filter
    flt = None
    if strict_state and state:
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        flt = Filter(must=[FieldCondition(key="state", match=MatchValue(value=state))])

    hits = qc.search(
        collection_name=coll,
        query_vector=vec,
        query_filter=flt,
        with_payload=True,
        limit=top_k,
    )

    results = []
    for h in hits:
        payload = h.payload or {}
        results.append({
            "text": payload.get("text", ""),
            "score": float(h.score) if hasattr(h, "score") else 0.0,
            "metadata": {
                "state": payload.get("state"),
                "source": payload.get("source"),
                "chunk_index": payload.get("chunk_index"),
                "line": payload.get("line"),
                "coverages": payload.get("coverages"),
                "section": payload.get("section"),
            }
        })
    return results


def rag_retrieve(*, state: str | None, topic: str = "general", k: int = 5, line: str | None = None,
                 coverage: str | None = None, coverages_any: list[str] | None = None,
                 section: str | None = None, user_query: str | None = None) -> list[str]:
    user_profile = {}  # not needed here, kept for API parity
    state_norm = state.upper() if state else None

    # seed text
    base_query_map = {
        "umbrella": "umbrella eligibility and underlying auto/home liability limits",
        "auto_adjust": "auto liability property damage comp collision UM UIM PIP rules",
        "general": "state insurance guidelines for auto and home",
    }
    seed = base_query_map.get((topic or "general"), "state insurance guidelines")
    q_prefix = f"{state_norm} " if state_norm else ""
    qtext = f"{q_prefix}{(user_query or seed)}".strip()

    # cache
    redis = current_app.config["SESSION_REDIS"]
    cov_key = ",".join(coverages_any or [])
    cache_key = f"rag:{state_norm or 'UNK'}:{topic}:{line}:{coverage}:{cov_key}:{hash(qtext)}:{k}"
    try:
        cached = redis.get(cache_key)
        if cached:
            return json.loads(cached.decode("utf-8") if isinstance(cached, (bytes, bytearray)) else cached)
    except Exception:
        pass

    hits = search(qtext, state=state_norm, top_k=k, line=line, topic=topic, coverages_any=coverages_any,
                  section=section, allow_fallbacks=False, strict_state=True)

    chunks = []
    for h in hits or []:
        meta = h.get("metadata", {}) or {}
        src = f"{(meta.get('state') or '')}:{(meta.get('source') or '')}#{meta.get('chunk_index')}"
        txt = (h.get("text") or "").strip()
        if not txt:
            continue
        tags = []
        if meta.get("line"):
            tags.append(meta["line"])
        if meta.get("coverages"):
            try:
                tags.extend(meta["coverages"])
            except Exception:
                pass
        if meta.get("section"):
            tags.append(meta["section"])
        tag_str = f" ({', '.join(tags)})" if tags else ""
        chunks.append(f"[{src}{tag_str}]\n{txt}")

    if chunks:
        try:
            redis.setex(cache_key, timedelta(minutes=3), json.dumps(chunks))
        except Exception:
            pass
    return chunks
