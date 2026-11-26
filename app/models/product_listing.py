from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class ProductListing(db.Model):
    """A single retailer's listing for a product — price, URL, offers, stock."""

    __tablename__ = "product_listings"

    id = db.Column(db.Integer, primary_key=True)

    product_id = db.Column(
        db.Integer, db.ForeignKey("products.id"), nullable=False, index=True
    )
    retailer_id = db.Column(
        db.Integer, db.ForeignKey("retailers.id"), nullable=False, index=True
    )

    # What the retailer calls it (may differ from our canonical name)
    product_name = db.Column(db.String(500), nullable=False)
    product_url = db.Column(db.String(1000), nullable=False)
    image_url = db.Column(db.String(1000), nullable=True)

    # Pricing — all in INR
    mrp = db.Column(db.Numeric(12, 2), nullable=True)
    selling_price = db.Column(db.Numeric(12, 2), nullable=False)
    discount = db.Column(db.Numeric(12, 2), nullable=True)
    currency = db.Column(db.String(10), default="INR", nullable=False)

    # Stock
    availability = db.Column(db.String(50), default="unknown", nullable=False)

    # Seller / marketplace info (some retailers are multi-seller)
    seller = db.Column(db.String(200), nullable=True)

    # Reviews
    rating = db.Column(db.Float, nullable=True)
    review_count = db.Column(db.Integer, nullable=True)

    # Offers — raw text as the retailer shows it
    offer_text = db.Column(db.Text, nullable=True)
    offer_type = db.Column(db.String(100), nullable=True)  # "bank", "exchange", "emi"
    bank = db.Column(db.String(100), nullable=True)
    offer_discount = db.Column(db.Numeric(12, 2), nullable=True)

    # EMI info from the retailer (not our calculation)
    emi_available = db.Column(db.Boolean, nullable=True)
    emi_tenure = db.Column(db.Integer, nullable=True)        # months
    emi_rate = db.Column(db.Float, nullable=True)             # annual %
    emi_monthly = db.Column(db.Numeric(12, 2), nullable=True)

    # Scrape metadata
    crawl_id = db.Column(db.String(100), nullable=True, index=True)
    scraped_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, nullable=False
    )

    created_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    # Relationships
    product = db.relationship("Product", back_populates="listings")
    retailer = db.relationship("Retailer", back_populates="listings")
    price_history = db.relationship(
        "PriceHistory", back_populates="listing", lazy="dynamic",
        order_by="PriceHistory.recorded_at.desc()"
    )

    def __repr__(self):
        return f"<ProductListing {self.id} {self.product_name[:40]} @ {self.selling_price}>"
