from datetime import datetime, timezone

from app.extensions import db


def _utcnow():
    return datetime.now(timezone.utc)


class Product(db.Model):
    """Canonical smartphone variant (brand + model + storage + colour)."""

    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)

    brand = db.Column(db.String(100), nullable=False, index=True)
    model = db.Column(db.String(200), nullable=False, index=True)
    storage = db.Column(db.String(50), nullable=True)
    colour = db.Column(db.String(100), nullable=True)
    sku = db.Column(db.String(100), nullable=True)

    # Normalized slug built from brand/model/storage/colour.
    # Prevents duplicate rows for the same phone variant.
    variant_id = db.Column(db.String(300), unique=True, nullable=False)

    created_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    listings = db.relationship("ProductListing", back_populates="product", lazy="dynamic")

    def __repr__(self):
        return f"<Product {self.id} {self.brand} {self.model} {self.storage}>"
