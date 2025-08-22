from __future__ import annotations
import os


class Config:
    # Flask
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB uploads

    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # OpenAI
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

    # Google Cloud (Vision + Storage)
    GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "{}")
    GCS_INPUT_BUCKET = os.getenv("GCS_INPUT_BUCKET")
    GCS_OUTPUT_BUCKET = os.getenv("GCS_OUTPUT_BUCKET")

    # Qdrant
    QDRANT_URL = os.getenv("QDRANT_URL", "")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
    QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "state_guidelines")

    # RAG
    RAG_TOP_K = int(os.getenv("RAG_TOP_K", "8"))
