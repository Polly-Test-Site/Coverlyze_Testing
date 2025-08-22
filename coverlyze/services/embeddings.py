from __future__ import annotations
from typing import List
from flask import current_app


def embed_texts(texts: List[str]) -> List[list[float]]:
    client = current_app.config["OPENAI_CLIENT"]
    resp = client.embeddings.create(model="text-embedding-3-large", input=texts)
    return [d.embedding for d in resp.data]
