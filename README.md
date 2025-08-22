# Coverlyze (Refactored)

A modular Flask app designed for DigitalOcean App Platform + Redis + Qdrant.
It ingests insurance dec pages, runs OCR when needed, retrieves state guidelines via RAG, and chats with users.

## Structure
```
coverlyze_refactor/
  coverlyze/
    __init__.py          # app factory + blueprint registration
    config.py            # env-driven settings
    extensions.py        # singletons (Redis, OpenAI, Qdrant, Google)
    routes/
      main.py            # index + small helpers
      chat.py            # /chat, /upload, debug endpoints, RAG
    services/
      ocr.py             # smart OCR (pdfplumber -> Vision fallback)
      dec_parser.py      # extract policy/vehicle/driver data + parse minimums
      rag.py             # Qdrant search + result formatting
      embeddings.py      # OpenAI embeddings helper
      llm.py             # system prompts & message builder
    utils/
      state.py           # state inference (+debug)
      chat_flow.py       # umbrella flow logic
  templates/
    index.html
  static/
  wsgi.py
  Procfile
  gunicorn.conf.py
  requirements.txt
  .env.example
  README.md
```

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export FLASK_SECRET_KEY=dev
export REDIS_URL=redis://localhost:6379/0
export OPENAI_API_KEY=sk-...
export QDRANT_URL=...
export QDRANT_API_KEY=...
export QDRANT_COLLECTION=state_guidelines
export GCS_INPUT_BUCKET=...
export GCS_OUTPUT_BUCKET=...
export GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ... }'

gunicorn -c gunicorn.conf.py wsgi:app
```

## Deploy to DigitalOcean App Platform
- Create a new app from this repo.
- Set **Run Command** to: `gunicorn -c gunicorn.conf.py wsgi:app`
- Add all environment variables from `.env.example` (use DO secrets for keys).
- Add a Redis database and set `REDIS_URL` (use `rediss://` if TLS required).
- Ensure your Qdrant URL/API key are reachable from DO.
- Health check: `/healthz` should return `{"ok":true}`

## Notes
- OCR uses Vision async GCS pipeline; set both input/output buckets and a service account.
- RAG retrieval caches results in Redis for 3 minutes to cut latency.
- Debug endpoints:
  - `/debug_ma_limits`
  - `/debug_qdrant`
  - `/rag_search?q=...&state=MA`
```

