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
from app.scrapers import CromaScraper, RelianceDigitalScraper, VijaySalesScraper
from app.services.emi_service import EmiService
from app.services.matching_service import MatchingService

logger = logging.getLogger(__name__)


class SearchService:

    def __init__(self):
        self.matching = MatchingService()
        self.emi_service = EmiService()
        # Initialize scrapers
        self.scrapers = [
            VijaySalesScraper(),
            CromaScraper(),
            RelianceDigitalScraper(),
        ]

    def execute_search(
        self,
        query: str,
        tenure: int = 12,
        down_payment: float = 0.0,
        annual_rate: float = 14.0,
    ) -> dict:
        """Run multi-retailer search, group by variant, and calculate best deals."""
        all_scraped = []

        # 1. Collect listings across retailers
        for scraper in self.scrapers:
            try:
                listings = scraper.search(query)
                all_scraped.extend(listings)
            except Exception as exc:
                logger.warning("Scraper %s failed during search: %s", scraper.name, exc)

        # 2. Group listings by canonical product variant
        grouped_variants = {}
        for item in all_scraped:
            norm = self.matching.normalize_listing(item)
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
                    continue

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

                # Calculate indicative EMI
                emi_info = self.emi_service.calculate_emi(
                    price=item.selling_price,
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
                    "mrp": item.mrp,
                    "discount": item.discount,
                    "availability": item.availability,
                    "offer_text": item.offer_text,
                    "emi": emi_info,
                })

            # Sort listings for this phone variant by selling price (lowest first)
            priced_listings = [l for l in formatted_listings if l["selling_price"] > 0]
            unpriced_listings = [l for l in formatted_listings if l["selling_price"] <= 0]
            sorted_listings = sorted(priced_listings, key=lambda x: x["selling_price"]) + unpriced_listings

            best_deal = sorted_listings[0] if sorted_listings else None

            results.append({
                "product_id": product.id,
                "variant_id": product.variant_id,
                "brand": product.brand,
                "model": product.model,
                "storage": product.storage,
                "colour": product.colour,
                "best_deal": best_deal,
                "listings": sorted_listings,
            })

        db.session.commit()

        return {
            "query": query,
            "total_variants": len(results),
            "results": results,
        }
