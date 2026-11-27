"""HTML UI page routes."""

from flask import Blueprint, render_template, request

from app.services.search_service import SearchService

pages_bp = Blueprint("pages", __name__)
search_service = SearchService()


@pages_bp.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@pages_bp.route("/results", methods=["GET"])
def results():
    query = request.args.get("query", "").strip()
    tenure = int(request.args.get("tenure") or 12)
    down_payment = float(request.args.get("down_payment") or 0.0)
    annual_rate = float(request.args.get("annual_rate") or 14.0)
    storage = request.args.get("storage", "").strip() or None
    colour = request.args.get("colour", "").strip() or None
    source = request.args.get("source", "").strip() or None
    raw_min = request.args.get("min_budget", "").strip()
    raw_max = request.args.get("max_budget", "").strip()
    min_budget = float(raw_min) if raw_min else None
    max_budget = float(raw_max) if raw_max else None

    filters = {
        "storage": storage,
        "colour": colour,
        "min_budget": min_budget,
        "max_budget": max_budget,
        "source": source if source and source != "all" else None,
    }

    if not query:
        return render_template("results.html", query="", results=[], total_variants=0, tenure=tenure, filters=filters)

    search_data = search_service.execute_search(
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

    return render_template(
        "results.html",
        query=query,
        results=search_data.get("results", []),
        total_variants=search_data.get("total_variants", 0),
        tenure=tenure,
        filters=filters,
    )
