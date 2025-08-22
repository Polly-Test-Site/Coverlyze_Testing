from __future__ import annotations
from io import BytesIO
import json
import re
import uuid

from flask import current_app
from google.cloud.vision_v1 import AnnotateFileResponse


def normalize_ocr_text(text: str) -> str:
    if not text:
        return text
    text = (text.replace('\ufb01', 'fi')
                .replace('\ufb02', 'fl')
                .replace('\ufb03', 'ffi')
                .replace('\ufb04', 'ffl'))
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\r?\n+', '\n', text)
    return text.strip()


def needs_ocr(text: str) -> bool:
    if not text or len(text.strip()) < 100:
        return True
    alnum = sum(c.isalnum() for c in text)
    if alnum / max(1, len(text)) < 0.3:
        return True
    words = text.split()
    single_chars = sum(1 for w in words if len(w) == 1)
    if len(words) > 0 and single_chars / len(words) > 0.3:
        return True
    return False


def extract_text_with_pdfplumber(pdf_file) -> str:
    import pdfplumber
    with pdfplumber.open(pdf_file) as pdf:
        text = "\n".join([page.extract_text() or "" for page in pdf.pages])
    return text


def vision_pdf_ocr(pdf_bytes: bytes, timeout_s: int = 300, delete_after: bool = True) -> str:
    vc = current_app.config.get("VISION_CLIENT")
    sc = current_app.config.get("STORAGE_CLIENT")
    input_bucket = current_app.config.get("GCS_INPUT_BUCKET")
    output_bucket = current_app.config.get("GCS_OUTPUT_BUCKET")
    if not vc or not sc:
        raise RuntimeError("Google clients not initialized")
    if not input_bucket or not output_bucket:
        raise RuntimeError("GCS_INPUT_BUCKET/GCS_OUTPUT_BUCKET not configured")

    # Upload
    in_bkt = sc.bucket(input_bucket)
    out_bkt = sc.bucket(output_bucket)
    in_name = f"input/{uuid.uuid4()}.pdf"
    in_blob = in_bkt.blob(in_name)
    in_blob.upload_from_string(pdf_bytes, content_type="application/pdf")

    feature = {"type_": 1}  # DOCUMENT_TEXT_DETECTION
    gcs_source = {"uri": f"gs://{input_bucket}/{in_name}"}
    gcs_dest_prefix = f"vision-output/{uuid.uuid4()}"
    gcs_dest_uri = f"gs://{output_bucket}/{gcs_dest_prefix}/"

    request = {
        "features": [feature],
        "input_config": {"gcs_source": gcs_source, "mime_type": "application/pdf"},
        "output_config": {"gcs_destination": {"uri": gcs_dest_uri}, "batch_size": 50},
    }
    op = vc.async_batch_annotate_files(requests=[request])
    op.result(timeout=timeout_s)

    texts = []
    for blob in current_app.config["STORAGE_CLIENT"].list_blobs(out_bkt, prefix=gcs_dest_prefix + "/"):
        data = blob.download_as_bytes()
        resp = AnnotateFileResponse.from_json(data.decode("utf-8"))
        for r in resp.responses:
            if r.full_text_annotation and r.full_text_annotation.text:
                texts.append(r.full_text_annotation.text)
    full = "\n\n--- PAGE BREAK ---\n\n".join(texts).strip()

    if delete_after:
        try:
            in_blob.delete()
            for blob in current_app.config["STORAGE_CLIENT"].list_blobs(out_bkt, prefix=gcs_dest_prefix + "/"):
                blob.delete()
        except Exception:
            pass

    return normalize_ocr_text(full)


def extract_text_smart(pdf_file) -> str:
    pdf_file.seek(0)
    base = extract_text_with_pdfplumber(pdf_file)
    if not needs_ocr(base):
        return normalize_ocr_text(base)
    pdf_file.seek(0)
    text = vision_pdf_ocr(pdf_file.read(), timeout_s=300)
    if not text:
        pdf_file.seek(0)
        return normalize_ocr_text(extract_text_with_pdfplumber(pdf_file))
    return text
