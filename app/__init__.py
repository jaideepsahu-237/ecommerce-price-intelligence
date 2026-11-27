import logging
import os
import time
from logging.handlers import RotatingFileHandler

from flask import Flask, g, request
from app.config import Config
from app.extensions import db


def _configure_api_logging(app: Flask):
    """Configure rotating file logging for all incoming API/web requests."""
    log_dir = os.path.join(os.path.dirname(app.root_path), "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "api.log")

    api_logger = logging.getLogger("api_calls")
    api_logger.setLevel(logging.INFO)
    if not api_logger.handlers:
        handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        api_logger.addHandler(handler)

    @app.before_request
    def _start_timer():
        g._req_start = time.perf_counter()

    @app.after_request
    def _log_request(response):
        elapsed_ms = (time.perf_counter() - getattr(g, "_req_start", time.perf_counter())) * 1000
        qs = f"?{request.query_string.decode('utf-8', errors='replace')}" if request.query_string else ""
        api_logger.info(
            "%s %s%s -> %s (%.1fms) | ip=%s",
            request.method,
            request.path,
            qs,
            response.status_code,
            elapsed_ms,
            request.remote_addr,
        )
        return response


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    _configure_api_logging(app)

    # Import models here (not at the top) to avoid circular imports.
    from app import models  # noqa: F401

    # Register Blueprints
    from app.routes.search import search_bp
    from app.routes.health import health_bp
    from app.routes.pages import pages_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(health_bp)

    return app
