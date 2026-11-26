"""Reliance Digital scraper adapter.

Fetches product listings from Reliance Digital category pages or search.
Parses structured JSON-LD or HTML DOM elements (product cards, prices,
ratings, availability).
"""

import json
import logging
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.config import Config
from app.scrapers.base import BaseScraper, ScrapedListing
from app.scrapers.croma import _extract_price, _parse_product_name, _to_float, _to_int

logger = logging.getLogger(__name__)


class RelianceDigitalScraper(BaseScraper):

    name = "reliance-digital"
    base_url = Config.RELIANCE_DIGITAL_BASE_URL
    category_url = Config.RELIANCE_DIGITAL_CATEGORY_URL
    request_interval = 2.0

    def __init__(
        self,
        base_url: Optional[str] = None,
        category_url: Optional[str] = None,
    ):
        super().__init__(base_url=base_url or Config.RELIANCE_DIGITAL_BASE_URL)
        self.category_url = category_url or Config.RELIANCE_DIGITAL_CATEGORY_URL

    def search(self, query: str, **filters) -> list[ScrapedListing]:
        """Search Reliance Digital for products matching query."""
        crawl_id = self._make_crawl_id()
        logger.info("%s: searching for '%s'", self.name, query)

        # Primary attempt: fetch from category URL (configured via .env)
        try:
            resp = self._get(self.category_url)
        except Exception as exc:
            logger.warning("%s: category request failed: %s", self.name, exc)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # 1. Try structured data JSON-LD
        listings = self._extract_jsonld(soup, crawl_id)

        # 2. Fall back to DOM elements
        if not listings:
            listings = self._extract_dom(soup, crawl_id)

        # Filter by search terms if a query is given
        if query:
            q_terms = query.lower().split()
            filtered = [
                l for l in listings
                if all(term in l.product_name.lower() for term in q_terms)
            ]
            logger.info(
                "%s: %d total listings found, %d match '%s'",
                self.name, len(listings), len(filtered), query
            )
            return filtered

        return listings

    def _extract_jsonld(self, soup: BeautifulSoup, crawl_id: str) -> list[ScrapedListing]:
        """Extract product listings from JSON-LD schema blocks."""
        results = []
        for script_tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script_tag.string or "")
            except (json.JSONDecodeError, TypeError):
                continue

            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "Product":
                    listing = self._parse_jsonld_product(item, crawl_id)
                    if listing:
                        results.append(listing)
                elif item.get("@type") == "ItemList":
                    for elem in item.get("itemListElement", []):
                        prod = elem.get("item", elem)
                        if isinstance(prod, dict):
                            name = prod.get("name") or elem.get("name")
                            url = prod.get("url") or elem.get("url")
                            offers = prod.get("offers", {})
                            price = _to_float(offers.get("price")) if isinstance(offers, dict) else None
                            if name:
                                brand, model, storage, colour = _parse_product_name(name)
                                full_url = url if (url and url.startswith("http")) else (self.base_url + (url or ""))
                                results.append(ScrapedListing(
                                    product_name=name,
                                    product_url=full_url,
                                    source=self.name,
                                    selling_price=price or 0.0,
                                    brand=brand,
                                    model=model,
                                    storage=storage,
                                    colour=colour,
                                    crawl_id=crawl_id,
                                ))

        return results

    def _parse_jsonld_product(self, item: dict, crawl_id: str) -> Optional[ScrapedListing]:
        try:
            name = item.get("name", "").strip()
            offers = item.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}

            selling = _to_float(offers.get("price"))
            if not name or selling is None:
                return None

            product_url = offers.get("url") or item.get("url", "")
            if product_url and not product_url.startswith("http"):
                product_url = self.base_url + product_url

            avail_url = offers.get("availability", "")
            availability = "in_stock" if "InStock" in avail_url else (
                "out_of_stock" if "OutOfStock" in avail_url else "unknown"
            )

            agg = item.get("aggregateRating", {})
            rating = _to_float(agg.get("ratingValue"))
            review_count = _to_int(agg.get("reviewCount"))

            images = item.get("image", [])
            image_url = images[0] if isinstance(images, list) and images else (
                images if isinstance(images, str) else None
            )

            brand_data = item.get("brand", {})
            brand_name = brand_data.get("name") if isinstance(brand_data, dict) else brand_data
            parsed_brand, model, storage, colour = _parse_product_name(name)

            return ScrapedListing(
                product_name=name,
                product_url=product_url,
                source=self.name,
                selling_price=selling,
                brand=parsed_brand or brand_name,
                model=model,
                storage=storage,
                colour=colour,
                sku=item.get("sku"),
                image_url=image_url,
                availability=availability,
                rating=rating,
                review_count=review_count,
                crawl_id=crawl_id,
            )
        except Exception as exc:
            logger.warning("%s: failed to parse JSON-LD product: %s", self.name, exc)
            return None

    def _extract_dom(self, soup: BeautifulSoup, crawl_id: str) -> list[ScrapedListing]:
        """Extract product cards from Reliance Digital DOM."""
        results = []

        card_selectors = [
            "li.grid",
            "div.sp",
            "div.plp-container li",
            "div[data-testid='product-card']",
            "div.product-card",
        ]

        cards = []
        for selector in card_selectors:
            cards = soup.select(selector)
            if cards:
                break

        if not cards:
            logger.warning("%s: no product cards found in DOM", self.name)
            return []

        for card in cards:
            listing = self._parse_dom_card(card, crawl_id)
            if listing:
                results.append(listing)

        return results

    def _parse_dom_card(self, card, crawl_id: str) -> Optional[ScrapedListing]:
        try:
            name_el = (
                card.select_one(".pbc__title")
                or card.select_one(".sp__name")
                or card.select_one("h3")
                or card.select_one("h2")
                or card.select_one("a[title]")
            )
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                return None

            link_el = card.select_one("a[href]")
            href = link_el["href"] if link_el else ""
            product_url = href if href.startswith("http") else self.base_url + href

            price_el = (
                card.select_one(".gimCrs")
                or card.select_one(".text__sellingPrice")
                or card.select_one(".sp__price")
                or card.select_one(".amount")
            )
            selling = _extract_price(price_el.get_text() if price_el else "")
            if selling is None:
                return None

            mrp_el = card.select_one(".text__mrp") or card.select_one(".sp__mrp")
            mrp = _extract_price(mrp_el.get_text() if mrp_el else "")
            discount = round(mrp - selling, 2) if mrp and mrp > selling else None

            img_el = card.select_one("img")
            image_url = img_el.get("src") or img_el.get("data-src") if img_el else None

            brand, model, storage, colour = _parse_product_name(name)

            return ScrapedListing(
                product_name=name,
                product_url=product_url,
                source=self.name,
                selling_price=selling,
                brand=brand,
                model=model,
                storage=storage,
                colour=colour,
                image_url=image_url,
                mrp=mrp,
                discount=discount,
                crawl_id=crawl_id,
            )
        except Exception as exc:
            logger.warning("%s: failed to parse DOM card: %s", self.name, exc)
            return None
