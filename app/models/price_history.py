from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class PriceHistory(db.Model):
    """A price snapshot for a listing, recorded each time we scrape it."""

    __tablename__ = "price_history"

    id = db.Column(db.Integer, primary_key=True)

    listing_id = db.Column(
        db.Integer, db.ForeignKey("product_listings.id"), nullable=False, index=True
    )

    mrp = db.Column(db.Numeric(12, 2), nullable=True)
    selling_price = db.Column(db.Numeric(12, 2), nullable=False)
    discount = db.Column(db.Numeric(12, 2), nullable=True)
    offer_text = db.Column(db.Text, nullable=True)

    crawl_id = db.Column(db.String(100), nullable=True, index=True)
    source_url = db.Column(db.String(1000), nullable=True)
    recorded_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, nullable=False, index=True
    )

    listing = db.relationship("ProductListing", back_populates="price_history")

    def __repr__(self):
        return f"<PriceHistory {self.id} listing={self.listing_id} ₹{self.selling_price} @ {self.recorded_at}>"
