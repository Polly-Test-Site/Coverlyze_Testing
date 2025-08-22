from __future__ import annotations

import json
import logging
import os
from typing import Optional

import redis
from flask import current_app
from google.cloud import storage
from google.cloud import vision_v1 as vision
from google.oauth2 import service_account
from openai import OpenAI
from qdrant_client import QdrantClient

logger = logging.getLogger(__name__)

_openai_client: Optional[OpenAI] = None
_qdrant_client: Optional[QdrantClient] = None
_redis_client: Optional[redis.Redis] = None
_vision_client: Optional[vision.ImageAnnotatorClient] = None
_storage_client: Optional[storage.Client] = None


def redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), decode_responses=False)
    return _redis_client


def openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(url=os.getenv("QDRANT_URL"), api_key=os.getenv("QDRANT_API_KEY"))
    return _qdrant_client


def google_clients():
    global _vision_client, _storage_client
    if _vision_client and _storage_client:
        return _vision_client, _storage_client

    try:
        info = json.loads(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}"))
        creds = service_account.Credentials.from_service_account_info(info) if info else None
        _vision_client = vision.ImageAnnotatorClient(credentials=creds) if creds else vision.ImageAnnotatorClient()
        _storage_client = storage.Client(credentials=creds) if creds else storage.Client()
    except Exception as e:
        logger.error("Failed to init Google clients: %s", e)
        _vision_client, _storage_client = None, None

    return _vision_client, _storage_client


def init_extensions(app):
    # attach helpful handles on app.config
    app.config["OPENAI_CLIENT"] = openai_client()
    app.config["QDRANT_CLIENT"] = qdrant_client()
    app.config["SESSION_REDIS"] = redis_client()
    vc, sc = google_clients()
    app.config["VISION_CLIENT"] = vc
    app.config["STORAGE_CLIENT"] = sc
