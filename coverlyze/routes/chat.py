from __future__ import annotations

import json
import logging
import random
import re
from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request, session

from ..extensions import openai_client, qdrant_client
from ..services.llm import build_messages, convert_markdown_to_html, llm_phrase, with_instruction
from ..services.dec_parser import extract_dec_page_data, parse_minimums_from_chunks
from ..services.ocr import extract_text_smart
from ..services.rag import rag_retrieve
from ..utils.chat_flow import (UMBRELLA_QUESTIONS, absorb_umbrella_answers_from_text,
                               estimate_umbrella_premium, next_missing_slot)
from ..utils.state import infer_state, infer_state_debug

logger = logging.getLogger(__name__)
bp = Blueprint("chat", __name__)

# --------- helpers ---------
def detect_target_coverage(user_text: str) -> str | None:
    t = (user_text or "").lower()
    if "property damage" in t or re.search(r"\bpd\b", t): return "property_damage"
    if "bodily injury" in t or re.search(r"\bbi\b", t): return "bodily_injury"
    if "underinsured" in t or re.search(r"\buim\b", t): return "uim"
    if "uninsured" in t or re.search(r"\bum\b", t): return "um"
    if "pip" in t: return "pip"
    if "medical payments" in t or "med pay" in t: return "medpay"
    return None


def generate_fake_rates(base_premium):
    try:
        base = float(str(base_premium).replace(",", "").strip()) if base_premium else 1200.0
    except Exception:
        base = 1200.0
    carriers = ["Travelers", "Geico", "Progressive", "Safeco", "Nationwide"]
    return {c: round(base * (1 + random.uniform(-0.1, 0.1)), 2) for c in carriers}


# --------- routes ----------
@bp.post("/upload")
def upload_file():
    try:
        if "file" not in request.files or not request.files["file"].filename:
            return jsonify({"error": "No file uploaded"}), 400
        f = request.files["file"]
        if not f.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Please upload a PDF file"}), 400

        extracted_text = extract_text_smart(f)
        session["extracted_text"] = extracted_text

        extracted_data = extract_dec_page_data(extracted_text)
        session["extracted_data"] = extracted_data

        premium = extracted_data.get("policy_info", {}).get("full_term_premium", "1200")
        session["fake_quotes"] = generate_fake_rates(premium)

        # quick summary with LLM (optional)
        client = openai_client()
        messages = [
            {"role": "system", "content": with_instruction("You are a professional insurance agent.",
                                                           "Output valid HTML with a Coverage Analysis table.")},
            {"role": "user", "content": f"Analyze this declarations page and provide recommendations in HTML:\n\n{extracted_text}"}
        ]
        try:
            resp = client.chat.completions.create(model="gpt-4o", messages=messages, max_tokens=1200, temperature=0.6)
            auto_summary = resp.choices[0].message.content
        except Exception as e:
            auto_summary = f"<p><em>Summary unavailable:</em> {e}</p>"

        session.setdefault("chat_history", [])
        session["chat_history"].append(("assistant", auto_summary))
        session["dec_summary"] = auto_summary

        return jsonify({"success": True, "extracted_data": extracted_data, "fake_quotes": session["fake_quotes"],
                        "auto_summary": auto_summary})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bp.post("/chat")
def chat():
    try:
        data = request.get_json() or {}
        user_message = (data.get("message") or "").strip()
        if not user_message:
            return jsonify({"error": "No message provided"}), 400

        session.setdefault("chat_history", [])
        session.setdefault("running_summary", "")
        session.setdefault("active_flow", None)
        session.setdefault("umbrella_slots", {})

        session["chat_history"].append(("user", user_message))

        # enter umbrella flow if asked
        if session["active_flow"] is None and re.search(r"\b(umbrella|pup|excess liability)\b", user_message, re.I):
            session["active_flow"] = "umbrella"

        # UMBRELLA FLOW
        if session.get("active_flow") == "umbrella":
            slots = session.get("umbrella_slots", {})
            slots = absorb_umbrella_answers_from_text(slots, user_message)
            missing = next_missing_slot(slots)
            if missing:
                session["umbrella_slots"] = slots
                q = UMBRELLA_QUESTIONS[missing]
                phrased = llm_phrase("Keep tone warm, professional, concise.", q)
                session["chat_history"].append(("assistant", phrased))
                session["running_summary"] += f"\n- U: {user_message[:160]} | A: {phrased[:160]}"
                session["chat_history"] = session["chat_history"][-12:]
                return jsonify({"success": True, "response": phrased})

            one_m, two_m = estimate_umbrella_premium(slots)
            session["active_flow"] = None
            session["umbrella_slots"] = slots
            html = (
                "<h4>Umbrella Quote Estimate</h4>"
                "<table><thead><tr><th>Limit</th><th>Estimated Annual Premium</th></tr></thead>"
                f"<tbody><tr><td>$1,000,000</td><td>${one_m}</td></tr>"
                f"<tr><td>$2,000,000</td><td>${two_m}</td></tr></tbody></table>"
                "<p>Want me to generate a firm quote with specific carriers?</p>"
            )
            session["chat_history"].append(("assistant", html))
            session["running_summary"] += f"\n- U: {user_message[:160]} | A: [umbrella table]"
            session["chat_history"] = session["chat_history"][-12:]
            return jsonify({"success": True, "response": html})

        # General path — RAG
        user_profile = session.get("user_profile") or {"preferred_tone": "concise, respectful"}
        session_state = infer_state(user_profile, session)
        target_cov = detect_target_coverage(user_message)

        retrieved_context = rag_retrieve(
            state=session_state, topic=session.get("active_flow") or "general", k=5,
            line=("auto" if (session.get("active_flow") or "general") == "auto_adjust" else None),
            coverage=None, coverages_any=None, section=None, user_query=user_message
        )

        state_norm = session_state.upper() if session_state else None
        allow_fallback = False
        if target_cov and state_norm:
            joined = "\n".join(retrieved_context).lower()
            need_terms_map = {
                "property_damage": ["property damage", "part 4", "pd liability"],
                "bodily_injury": ["bodily injury", "part 1", "part 5", "bi liability"],
                "um": ["uninsured", "um"], "uim": ["underinsured", "uim"],
                "pip": ["pip", "personal injury protection"], "medpay": ["medical payments", "med pay"],
            }
            need_terms = need_terms_map.get(target_cov, [])
            if not any(t in joined for t in need_terms):
                allow_fallback = True

        messages = build_messages(
            user_message=user_message, session_obj=session, user_profile=user_profile,
            retrieved_context=retrieved_context, flow_state=session.get("active_flow"),
            allow_pretraining_fallback=allow_fallback, state_norm=state_norm, target_cov=target_cov
        )

        client = openai_client()
        resp = client.chat.completions.create(model="gpt-4o", messages=messages, max_tokens=1000, temperature=0.4)
        reply = (resp.choices[0].message.content or "").strip()
        reply = convert_markdown_to_html(reply)
        session["chat_history"].append(("assistant", reply))
        session["running_summary"] += f"\n- U: {user_message[:160]} | A: {reply[:160]}"
        session["chat_history"] = session["chat_history"][-12:]

        return jsonify({"success": True, "response": reply})
    except Exception as e:
        logger.exception("chat error")
        error_msg = f"Error processing chat: {e}"
        session.setdefault("chat_history", []).append(("assistant", error_msg))
        return jsonify({"error": error_msg}), 500


@bp.get("/debug_ma_limits")
def debug_ma_limits():
    try:
        user_profile = session.get("user_profile") or {}
        st, dbg = infer_state_debug(user_profile, session)
        test_queries = [
            "Massachusetts minimum liability limits",
            "MA state minimum auto insurance",
            "Massachusetts bodily injury property damage limits"
        ]
        results = {}
        for q in test_queries:
            chunks = rag_retrieve(state="MA", topic="general", k=5, user_query=q)
            results[q] = {
                "chunks_found": len(chunks),
                "chunks": [c[:300] + "..." for c in chunks],
                "parsed_minimums": parse_minimums_from_chunks(chunks)
            }
        chunks_no = rag_retrieve(state=None, topic="general", k=5, user_query="Massachusetts minimum limits")
        return jsonify({
            "inferred_state": st, "state_debug_info": dbg, "user_profile": user_profile,
            "test_results": results, "no_state_chunks": len(chunks_no),
            "no_state_parsed": parse_minimums_from_chunks(chunks_no)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.post("/clear_cache")
def clear_cache():
    try:
        current_app.config["SESSION_REDIS"].flushdb()
        return jsonify({"success": True, "message": "Cache cleared"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.post("/set_ma_state")
def set_ma_state():
    try:
        profile = session.get("user_profile") or {}
        profile["state"] = "MA"
        session["user_profile"] = profile
        return jsonify({"success": True, "profile": profile})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.get("/rag_search")
def rag_search_route():
    q_state = request.args.get("state") or infer_state(session.get("user_profile") or {}, session)
    q_topic = request.args.get("topic", "general")
    q_k = int(request.args.get("k", "5"))
    q_line = request.args.get("line")
    q_coverage = request.args.get("coverage")
    q_coverages_any = request.args.getlist("coverages_any") or None
    q_section = request.args.get("section")
    q = request.args.get("q")

    chunks = rag_retrieve(state=q_state, topic=q_topic, k=q_k, line=q_line, coverage=q_coverage,
                          coverages_any=q_coverages_any, section=q_section, user_query=q)
    return jsonify({
        "state": q_state, "topic": q_topic, "k": q_k, "line": q_line, "coverage": q_coverage,
        "coverages_any": q_coverages_any, "section": q_section, "q": q, "chunks": chunks
    })


@bp.get("/debug_qdrant")
def debug_qdrant():
    try:
        qc = qdrant_client()
        coll = current_app.config.get("QDRANT_COLLECTION")
        info = qc.get_collection(coll)

        from qdrant_client.models import Filter, FieldCondition, MatchValue
        ma_filter = Filter(must=[FieldCondition(key="state", match=MatchValue(value="MA"))])
        points, _ = qc.scroll(collection_name=coll, scroll_filter=ma_filter, limit=10, with_payload=True)

        ma_limits_points = []
        for p in points:
            payload = p.payload or {}
            text = (payload.get("text") or "").lower()
            if "minimum" in text and any(x in text for x in ["25,000", "50,000", "30,000"]):
                ma_limits_points.append({
                    "id": p.id,
                    "text": (payload.get("text") or "")[:500],
                    "metadata": {k: v for k, v in payload.items() if k != "text"}
                })

        sample = [{
            "id": p.id,
            "text": (p.payload.get("text", "") if p.payload else "")[:200],
            "state": (p.payload.get("state", "") if p.payload else ""),
            "source": (p.payload.get("source", "") if p.payload else ""),
        } for p in points[:3]]

        return jsonify({
            "collection_info": {"points_count": info.points_count, "vectors_count": getattr(info, "vectors_count", None)},
            "ma_points_found": len(points),
            "ma_limits_points": ma_limits_points,
            "sample_ma_points": sample,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
