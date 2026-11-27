"""Search coordinator and persistence service.

Coordinates multi-retailer scraping, normalizes and groups matching products,
computes indicative EMI calculations, persists records in PostgreSQL,
and formats the ranked results for the API/UI.
"""

import logging
from decimal import Decimal
from typing import Optional

from app.extensions import db
from app.models import PriceHistory, Product, ProductListing, Retailer
from app.scrapers import PoorvikaScraper, RelianceDigitalScraper, VijaySalesScraper
from app.services.emi_service import EmiService, parse_offer_details
from app.services.matching_service import (
    MatchingService,
    correct_brand_typos,
    is_accessory,
    normalize_colour,
    normalize_storage,
)
from app.services.offer_enrichment import enrich_offers_with_playwright

logger = logging.getLogger(__name__)


class SearchService:

    def __init__(self):
        self.matching = MatchingService()
        self.emi_service = EmiService()
        # Initialize scrapers
        self.scrapers = [
            VijaySalesScraper(),
            RelianceDigitalScraper(),
            PoorvikaScraper(),
        ]

    def execute_search(
        self,
        query: str,
        tenure: int = 12,
        down_payment: float = 0.0,
        annual_rate: float = 14.0,
        storage: Optional[str] = None,
        colour: Optional[str] = None,
        min_budget: Optional[float] = None,
        max_budget: Optional[float] = None,
        source: Optional[str] = None,
    ) -> dict:
        """Run multi-retailer search, apply optional filters, group by variant, and calculate best deals."""
        # 0. Autocorrect typos in brand names (e.g. Samanung -> Samsung)
        clean_query = correct_brand_typos(query)
        if clean_query != query:
            logger.info("Autocorrected search query: '%s' -> '%s'", query, clean_query)

        source_filter = (source or "").strip().lower()
        if source_filter in ("", "all"):
            source_filter = None

        storage_filter = normalize_storage(storage, storage) if storage and storage.strip() else None
        if storage and storage.strip() and not storage_filter:
            storage_filter = storage.strip().upper()
        colour_filter = normalize_colour(colour) if colour and colour.strip() else None

        active_scrapers = [
            s for s in self.scrapers
            if not source_filter or s.name.lower() == source_filter
        ]

        all_scraped = []

        # 1. Collect live listings across selected retailers using corrected query
        for scraper in active_scrapers:
            try:
                listings = scraper.search(clean_query)
                all_scraped.extend(listings)
            except Exception as exc:
                logger.warning("Scraper %s failed during search: %s", scraper.name, exc)

        # Filter out cases, covers, chargers, and other accessories
        all_scraped = [
            item for item in all_scraped
            if not is_accessory(item.product_name, item.selling_price)
        ]

        # 2. Hybrid Search: If live scrapers return 0 items (e.g. WAF block or offline),
        # query previously saved products from PostgreSQL database
        if not all_scraped:
            logger.info("Live scrapers returned 0 items; falling back to PostgreSQL DB cache for '%s'", clean_query)
            query_words = [w for w in clean_query.split() if len(w) > 1]
            if query_words:
                conditions = [
                    (
                        Product.model.ilike(f"%{w}%")
                        | Product.brand.ilike(f"%{w}%")
                        | Product.listings.any(ProductListing.product_name.ilike(f"%{w}%"))
                    )
                    for w in query_words
                ]
                cached_products = Product.query.filter(*conditions).all()

                for p in cached_products:
                    for l in p.listings.all():
                        if source_filter and l.retailer and l.retailer.slug.lower() != source_filter:
                            continue
                        scraped = self.matching.listing_record_to_scraped(p, l)
                        if not is_accessory(scraped.product_name, scraped.selling_price):
                            all_scraped.append(scraped)

        # 3. Apply optional filters before Playwright enrichment & variant grouping
        filtered_items = []
        for item in all_scraped:
            norm = self.matching.normalize_listing(item)

            if storage_filter:
                item_storage = (norm["storage"] or "").replace(" ", "").lower()
                if item_storage != storage_filter.replace(" ", "").lower():
                    continue

            if colour_filter:
                item_colour = (norm["colour"] or "").lower()
                if colour_filter.lower() not in item_colour and colour_filter.lower() not in item.product_name.lower():
                    continue

            if min_budget is not None or max_budget is not None:
                price = item.selling_price or 0.0
                if price <= 0:
                    continue
                if min_budget is not None and price < min_budget:
                    continue
                if max_budget is not None and price > max_budget:
                    continue

            filtered_items.append((item, norm))

        # Enrich top filtered listings with client-side bank/card offers via Playwright
        enrich_offers_with_playwright([item for item, _ in filtered_items], max_per_retailer=5)

        grouped_variants = {}
        for item, norm in filtered_items:
            variant_id = norm["variant_id"]

            if variant_id not in grouped_variants:
                grouped_variants[variant_id] = {
                    "brand": norm["brand"],
                    "model": norm["model"],
                    "storage": norm["storage"],
                    "colour": norm["colour"],
                    "variant_id": variant_id,
                    "listings": [],
                }

            grouped_variants[variant_id]["listings"].append(item)

        # 3. Persist and rank deals
        results = []
        for variant_id, group in grouped_variants.items():
            # Get or create canonical Product in DB
            product = Product.query.filter_by(variant_id=variant_id).first()
            if not product:
                product = Product(
                    brand=group["brand"],
                    model=group["model"],
                    storage=group["storage"],
                    colour=group["colour"],
                    variant_id=variant_id,
                )
                db.session.add(product)
                db.session.flush()

            # Process listings for this variant
            formatted_listings = []
            for item in group["listings"]:
                retailer = Retailer.query.filter_by(slug=item.source).first()
                if not retailer:
                    retailer = Retailer(
                        name=item.source.replace("-", " ").title(),
                        slug=item.source,
                        base_url=f"https://www.{item.source.replace('-', '')}.com",
                    )
                    db.session.add(retailer)
                    db.session.flush()

                # Find or create listing
                listing_record = ProductListing.query.filter_by(
                    product_id=product.id,
                    retailer_id=retailer.id,
                ).first()

                price_dec = Decimal(str(item.selling_price)) if item.selling_price else Decimal("0.0")
                mrp_dec = Decimal(str(item.mrp)) if item.mrp else None
                discount_dec = Decimal(str(item.discount)) if item.discount else None

                if not listing_record:
                    listing_record = ProductListing(
                        product_id=product.id,
                        retailer_id=retailer.id,
                        product_name=item.product_name,
                        product_url=item.product_url,
                        image_url=item.image_url,
                        selling_price=price_dec,
                        mrp=mrp_dec,
                        discount=discount_dec,
                        availability=item.availability,
                        offer_text=item.offer_text,
                        crawl_id=item.crawl_id,
                    )
                    db.session.add(listing_record)
                    db.session.flush()
                else:
                    # Update existing listing
                    listing_record.selling_price = price_dec
                    listing_record.mrp = mrp_dec
                    listing_record.discount = discount_dec
                    listing_record.availability = item.availability
                    listing_record.offer_text = item.offer_text

                # Record price history snapshot
                if item.selling_price and item.selling_price > 0:
                    history = PriceHistory(
                        listing_id=listing_record.id,
                        mrp=mrp_dec,
                        selling_price=price_dec,
                        discount=discount_dec,
                        offer_text=item.offer_text,
                        source_url=item.product_url,
                        crawl_id=item.crawl_id,
                    )
                    db.session.add(history)

                # Extract offer details & compute effective price separately from selling_price
                parsed_disc, parsed_type, parsed_bank = parse_offer_details(
                    item.offer_text, item.selling_price or 0.0
                )
                offer_discount = item.offer_discount if item.offer_discount is not None else parsed_disc
                offer_type = item.offer_type or parsed_type
                bank = item.bank or parsed_bank
                effective_price = (
                    round(max(0.0, item.selling_price - (offer_discount or 0.0)), 2)
                    if item.selling_price and item.selling_price > 0
                    else 0.0
                )

                # Calculate indicative EMI
                emi_info = self.emi_service.calculate_emi(
                    price=effective_price or item.selling_price,
                    down_payment=down_payment,
                    tenure_months=tenure,
                    annual_rate=annual_rate,
                )

                formatted_listings.append({
                    "retailer": retailer.name,
                    "product_name": item.product_name,
                    "product_url": item.product_url,
                    "image_url": item.image_url,
                    "selling_price": item.selling_price,
                    "effective_price": effective_price,
                    "mrp": item.mrp,
                    "discount": item.discount,
                    "availability": item.availability,
                    "offer_text": item.offer_text,
                    "offer_type": offer_type,
                    "bank": bank,
                    "offer_discount": offer_discount,
                    "scraped_at": item.scraped_at,
                    "emi": emi_info,
                })

            # Sort listings for this phone variant by effective price, then selling price
            priced_listings = [l for l in formatted_listings if l["selling_price"] > 0]
            unpriced_listings = [l for l in formatted_listings if l["selling_price"] <= 0]
            sorted_listings = sorted(
                priced_listings, key=lambda x: (x["effective_price"], x["selling_price"])
            ) + unpriced_listings

            best_deal = sorted_listings[0] if sorted_listings else None
            ranking_reason = None
            if best_deal and best_deal["selling_price"] > 0:
                if best_deal.get("offer_discount"):
                    ranking_reason = (
                        f"Lowest effective price (₹{best_deal['effective_price']:,.2f} after "
                        f"₹{best_deal['offer_discount']:,.2f} offer) across {len(sorted_listings)} listing(s)"
                    )
                else:
                    ranking_reason = (
                        f"Lowest listed selling price (₹{best_deal['selling_price']:,.2f}) "
                        f"across {len(sorted_listings)} listing(s)"
                    )

            results.append({
                "product_id": product.id,
                "variant_id": product.variant_id,
                "brand": product.brand,
                "model": product.model,
                "storage": product.storage,
                "colour": product.colour,
                "best_deal": best_deal,
                "ranking_reason": ranking_reason,
                "listings": sorted_listings,
            })

        db.session.commit()

        return {
            "query": query,
            "total_variants": len(results),
            "results": results,
        }
