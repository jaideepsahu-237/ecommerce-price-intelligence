from flask import Flask
from app.config import Config
from app.extensions import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    # Import models here (not at the top) to avoid circular imports.
    from app import models  # noqa: F401

    # Register Blueprints
    from app.routes.search import search_bp
    from app.routes.health import health_bp

    app.register_blueprint(search_bp)
    app.register_blueprint(health_bp)

    @app.route("/")
    def home():
        return "Ecommerce Price Intelligence API is running!"

    return app
