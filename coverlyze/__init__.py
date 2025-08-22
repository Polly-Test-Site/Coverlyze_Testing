from __future__ import annotations

import logging
from datetime import timedelta
import os

from flask import Flask
from flask_session import Session

from .config import Config
from .extensions import init_extensions, redis_client
from .routes.main import bp as main_bp
from .routes.chat import bp as chat_bp

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """Application factory used by both local run and gunicorn/DO."""
    app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), "..", "templates"), 
                static_folder=os.path.join(os.path.dirname(__file__), "..", "static"))
    app.config.from_object(Config())

    # Sessions in Redis/Valkey
    app.config.update(
        SESSION_TYPE="redis",
        SESSION_REDIS=redis_client(),
        SESSION_PERMANENT=True,
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        SESSION_USE_SIGNER=True,
        SESSION_KEY_PREFIX="sess:",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False if os.getenv("FLASK_DEBUG") else True,
    )
    Session(app)

    # Init other singletons
    init_extensions(app)

    # Blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(chat_bp)

    # Basic health check
    @app.get("/healthz")
    def healthz():
        try:
            app.config["SESSION_REDIS"].ping()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}, 500

    return app
