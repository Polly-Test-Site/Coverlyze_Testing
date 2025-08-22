from __future__ import annotations
from flask import Blueprint, render_template, jsonify, session, send_file
import io, json

from ..services.ocr import extract_text_smart
from ..services.dec_parser import extract_dec_page_data
from ..services.llm import build_messages
from ..extensions import openai_client


bp = Blueprint("main", __name__)


@bp.get("/")
def index():
    session.clear()
    session["chat_history"] = []
    session["running_summary"] = ""
    return render_template("index.html")


@bp.get("/get_chat_history")
def get_chat_history():
    return jsonify({
        "chat_history": session.get("chat_history", []),
        "extracted_data": session.get("extracted_data", {}),
        "fake_quotes": session.get("fake_quotes", {})
    })


@bp.get("/clear_session")
def clear_session():
    session.clear()
    return jsonify({"success": True})


@bp.get("/download_json")
def download_json():
    extracted_data = session.get("extracted_data", {})
    json_data = json.dumps(extracted_data, indent=2)
    return send_file(io.BytesIO(json_data.encode("utf-8")), as_attachment=True, download_name="dec_page_extracted.json",
                     mimetype="application/json")
