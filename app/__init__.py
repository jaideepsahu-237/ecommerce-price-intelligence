from flask import Flask
from app.config import Config
from app.extensions import db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    # Import models here (not at the top) to avoid circular imports.
    from app import models  # noqa: F401

    @app.route("/")
    def home():
        return "Ecommerce Price Intelligence API is running!"

    return app
