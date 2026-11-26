from sqlalchemy import text

from app import create_app
from app.extensions import db

app = create_app()

with app.app_context():
    with db.engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        print("Database connected successfully:", result.scalar())