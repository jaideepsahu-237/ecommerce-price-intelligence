"""Search and comparison API routes."""

from flask import Blueprint, jsonify, request

from app.services.search_service import SearchService

search_bp = Blueprint("search", __name__, url_prefix="/api")
search_service = SearchService()


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
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid format for numeric parameters (tenure, down_payment, annual_rate)."}), 400

    results = search_service.execute_search(
        query=query,
        tenure=tenure,
        down_payment=down_payment,
        annual_rate=annual_rate,
    )

    return jsonify(results), 200
