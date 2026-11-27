"""Search and comparison API routes."""

from flask import Blueprint, jsonify, request

from app.models import PriceHistory, Product, ProductListing
from app.services.emi_service import EmiService
from app.services.search_service import SearchService

search_bp = Blueprint("search", __name__, url_prefix="/api")
search_service = SearchService()
emi_service = EmiService()


@search_bp.route("/search", methods=["POST", "GET"])
def search_products():
    """Search for smartphones and compare prices across retailers.

    Accepts JSON body (for POST) or query parameters (for GET):
        query: search string (e.g. "iPhone 17")
        tenure: EMI tenure in months (default: 12)
        down_payment: down payment amount in INR (default: 0.0)
        annual_rate: annual interest rate percentage (default: 14.0)
    """
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
    else:
        data = request.args.to_dict()

    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Search query parameter 'query' is required."}), 400

    try:
        tenure = int(data.get("tenure", 12))
        down_payment = float(data.get("down_payment", 0.0))
        annual_rate = float(data.get("annual_rate", 14.0))
        raw_min = data.get("min_budget")
        raw_max = data.get("max_budget", data.get("budget"))
        min_budget = float(raw_min) if raw_min not in (None, "") else None
        max_budget = float(raw_max) if raw_max not in (None, "") else None
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid format for numeric parameters (tenure, down_payment, annual_rate, min_budget, max_budget)."}), 400

    storage = (data.get("storage") or "").strip() or None
    colour = (data.get("colour") or "").strip() or None
    source = (data.get("source") or "").strip() or None

    results = search_service.execute_search(
        query=query,
        tenure=tenure,
        down_payment=down_payment,
        annual_rate=annual_rate,
        storage=storage,
        colour=colour,
        min_budget=min_budget,
        max_budget=max_budget,
        source=source,
    )

    return jsonify(results), 200


@search_bp.route("/product/<int:product_id>", methods=["GET"])
def get_product_details(product_id: int):
    """Return normalized product/variant details and its current retailer listings."""
    product = Product.query.get(product_id)
    if not product:
        return jsonify({"error": f"Product {product_id} not found."}), 404

    listings = []
    for l in product.listings.all():
        listings.append({
            "listing_id": l.id,
            "retailer": l.retailer.name if l.retailer else None,
            "retailer_slug": l.retailer.slug if l.retailer else None,
            "product_name": l.product_name,
            "product_url": l.product_url,
            "image_url": l.image_url,
            "selling_price": float(l.selling_price) if l.selling_price is not None else 0.0,
            "mrp": float(l.mrp) if l.mrp is not None else None,
            "discount": float(l.discount) if l.discount is not None else None,
            "currency": l.currency,
            "availability": l.availability,
            "rating": l.rating,
            "review_count": l.review_count,
            "scraped_at": l.scraped_at.isoformat() if l.scraped_at else None,
        })

    listings.sort(key=lambda x: (x["selling_price"] <= 0, x["selling_price"]))

    return jsonify({
        "product_id": product.id,
        "variant_id": product.variant_id,
        "brand": product.brand,
        "model": product.model,
        "storage": product.storage,
        "colour": product.colour,
        "listings": listings,
    }), 200


@search_bp.route("/offers/<int:product_id>", methods=["GET"])
def get_product_offers(product_id: int):
    """Return retailer offers and indicative EMI options for a product."""
    product = Product.query.get(product_id)
    if not product:
        return jsonify({"error": f"Product {product_id} not found."}), 404

    try:
        tenure = int(request.args.get("tenure", 12))
        down_payment = float(request.args.get("down_payment", 0.0))
        annual_rate = float(request.args.get("annual_rate", 14.0))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid format for numeric parameters (tenure, down_payment, annual_rate)."}), 400

    offers = []
    for l in product.listings.all():
        price = float(l.selling_price) if l.selling_price is not None else 0.0
        emi_calc = emi_service.calculate_emi(
            price=price,
            down_payment=down_payment,
            tenure_months=tenure,
            annual_rate=annual_rate,
        )
        offers.append({
            "listing_id": l.id,
            "retailer": l.retailer.name if l.retailer else None,
            "selling_price": price,
            "offer_text": l.offer_text,
            "offer_type": l.offer_type,
            "bank": l.bank,
            "offer_discount": float(l.offer_discount) if l.offer_discount is not None else None,
            "retailer_emi": {
                "available": l.emi_available,
                "tenure": l.emi_tenure,
                "rate": l.emi_rate,
                "monthly": float(l.emi_monthly) if l.emi_monthly is not None else None,
            },
            "calculated_emi": emi_calc,
        })

    return jsonify({
        "product_id": product.id,
        "variant_id": product.variant_id,
        "offers": offers,
    }), 200


@search_bp.route("/price-history/<int:product_id>", methods=["GET"])
def get_price_history(product_id: int):
    """Return historical price observations for a product across retailers."""
    product = Product.query.get(product_id)
    if not product:
        return jsonify({"error": f"Product {product_id} not found."}), 404

    rows = (
        PriceHistory.query
        .join(ProductListing, PriceHistory.listing_id == ProductListing.id)
        .filter(ProductListing.product_id == product_id)
        .order_by(PriceHistory.recorded_at.desc())
        .all()
    )

    history = [
        {
            "id": row.id,
            "listing_id": row.listing_id,
            "retailer": row.listing.retailer.name if row.listing and row.listing.retailer else None,
            "selling_price": float(row.selling_price) if row.selling_price is not None else 0.0,
            "mrp": float(row.mrp) if row.mrp is not None else None,
            "discount": float(row.discount) if row.discount is not None else None,
            "offer_text": row.offer_text,
            "source_url": row.source_url,
            "crawl_id": row.crawl_id,
            "recorded_at": row.recorded_at.isoformat() if row.recorded_at else None,
        }
        for row in rows
    ]

    return jsonify({
        "product_id": product.id,
        "variant_id": product.variant_id,
        "total_records": len(history),
        "history": history,
    }), 200
