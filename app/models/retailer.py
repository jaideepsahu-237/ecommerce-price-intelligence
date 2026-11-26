from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class Retailer(db.Model):
    """An ecommerce site we scrape (Croma, Vijay Sales, etc.)."""

    __tablename__ = "retailers"

    id = db.Column(db.Integer, primary_key=True)

    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(50), unique=True, nullable=False)  # e.g. "croma"
    base_url = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # Scraper tuning — seconds between requests to this retailer
    scrape_interval = db.Column(db.Float, default=2.0, nullable=False)

    created_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    listings = db.relationship("ProductListing", back_populates="retailer", lazy="dynamic")

    def __repr__(self):
        return f"<Retailer {self.id} {self.name}>"
