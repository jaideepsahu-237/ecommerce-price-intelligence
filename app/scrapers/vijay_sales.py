"""Vijay Sales scraper adapter.

Searches Vijay Sales for smartphones.
Handles path-based search (e.g. /search/{query}) and query parameters.
Parses structured JSON-LD (<script type="application/ld+json">) and HTML DOM
for product cards, pricing, availability, and ratings.
"""

import json
import logging
import re
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.config import Config
from app.scrapers.base import BaseScraper, ScrapedListing
from app.scrapers.croma import _extract_price, _parse_product_name, _to_float, _to_int

logger = logging.getLogger(__name__)


class VijaySalesScraper(BaseScraper):

    name = "vijay-sales"
    base_url = Config.VIJAY_SALES_BASE_URL
    category_url = Config.VIJAY_SALES_CATEGORY_URL
    search_api_url = "https://mdm.vijaysales.com/web/api/search/unbxd-search/v1"
    request_interval = 2.0

    def __init__(
        self,
        base_url: Optional[str] = None,
        category_url: Optional[str] = None,
    ):
        super().__init__(base_url=base_url or Config.VIJAY_SALES_BASE_URL)
        self.category_url = category_url or Config.VIJAY_SALES_CATEGORY_URL

    def search(self, query: str, **filters) -> list[ScrapedListing]:
        """Search Vijay Sales via its Unbxd JSON search API, with HTML fallback."""
        crawl_id = self._make_crawl_id()
        logger.info("%s: searching for '%s'", self.name, query)

        listings = self._search_via_api(query, crawl_id)
        if not listings:
            listings = self._search_via_html(query, crawl_id)

        if query and listings:
            q_terms = re.sub(r"[^\w\s]", "", query.lower()).split()
            listings = [
                l for l in listings
                if all(term in re.sub(r"[^\w\s]", "", l.product_name.lower()) for term in q_terms)
            ]

        logger.info("%s: returning %d listings for '%s'", self.name, len(listings), query)
        return listings

    def _search_via_api(self, query: str, crawl_id: str) -> list[ScrapedListing]:
        """Query Vijay Sales's Unbxd JSON search endpoint directly."""
        params = {
            "q": f"{query}&page=1&rows=30",
            "fq": "",
        }
        try:
            resp = self._get(self.search_api_url, params=params)
            data = resp.json()
        except Exception as exc:
            logger.warning("%s: Unbxd API request failed: %s", self.name, exc)
            return []

        products = data.get("response", {}).get("products", [])
        results = []
        for item in products:
            name = (item.get("title") or "").strip()
            selling = _to_float(
                item.get("offerPrice")
                or item.get("vsp")
                or item.get("price")
                or item.get("cityId_1_offerPrice_unx_d")
                or item.get("cityId_1_sellingPrice_unx_d")
                or item.get("cityId_1_price_unx_d")
            )
            if not name or selling is None:
                continue

            mrp = _to_float(item.get("mrp"))
            discount = round(mrp - selling, 2) if mrp and mrp > selling else None

            raw_url = item.get("productUrl") or ""
            product_url = raw_url if raw_url.startswith("http") else f"{self.base_url}{raw_url}"

            imgs = item.get("imageUrl")
            image_url = imgs[0] if isinstance(imgs, list) and imgs else (imgs if isinstance(imgs, str) else None)

            offer_parts = []
            if item.get("cityId_1_offerAvailable_unx_ts"):
                offer_parts.append(str(item["cityId_1_offerAvailable_unx_ts"]))
            exchange = item.get("cityId_1_exchange_unx_tsm")
            if isinstance(exchange, list) and exchange:
                offer_parts.append(f"Exchange: {', '.join(exchange)}")
            offer_text = " | ".join(offer_parts) if offer_parts else None

            brand, model, storage, colour = _parse_product_name(name)
            raw_brand = item.get("brand")
            if isinstance(raw_brand, list):
                raw_brand = raw_brand[0] if raw_brand else None
            results.append(ScrapedListing(
                product_name=name,
                product_url=product_url,
                source=self.name,
                selling_price=selling,
                brand=brand or (str(raw_brand).strip() if raw_brand else None),
                model=model,
                storage=storage,
                colour=colour,
                sku=item.get("sku") or item.get("uid"),
                image_url=image_url,
                mrp=mrp,
                discount=discount,
                offer_text=offer_text,
                rating=_to_float(item.get("aggregateAverageRating")),
                review_count=_to_int(item.get("aggregateReviewCount") or item.get("aggregateRatingCount")),
                crawl_id=crawl_id,
            ))

        logger.info("%s: Unbxd API extracted %d listings", self.name, len(results))
        return results

    def _search_via_html(self, query: str, crawl_id: str) -> list[ScrapedListing]:
        """Fallback to Vijay Sales /search-listing?q= HTML page."""
        search_url = f"{self.base_url}/search-listing?q={quote_plus(query)}"
        try:
            resp = self._get(search_url)
            if resp.status_code != 200:
                return []
            soup = BeautifulSoup(resp.text, "html.parser")
            return self._extract_dom(soup, crawl_id) or self._extract_jsonld(soup, crawl_id)
        except Exception as exc:
            logger.warning("%s: HTML search fallback failed: %s", self.name, exc)
            return []

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
                # Can be a single Product, or an ItemList (collection)
                if item.get("@type") == "Product":
                    listing = self._parse_jsonld_product(item, crawl_id)
                    if listing:
                        results.append(listing)
                elif item.get("@type") == "ItemList":
                    for elem in item.get("itemListElement", []):
                        prod = elem.get("item", elem)
                        if isinstance(prod, dict):
                            # In Vijay Sales, the element itself can have name and url
                            name = prod.get("name") or elem.get("name")
                            url = prod.get("url") or elem.get("url")
                            if name:
                                brand, model, storage, colour = _parse_product_name(name)
                                # Clean URL if relative
                                full_url = url if (url and url.startswith("http")) else (self.base_url + (url or ""))
                                results.append(ScrapedListing(
                                    product_name=name,
                                    product_url=full_url,
                                    source=self.name,
                                    selling_price=0.0,  # placeholder if not in category list schema
                                    brand=brand,
                                    model=model,
                                    storage=storage,
                                    colour=colour,
                                    crawl_id=crawl_id,
                                ))

        logger.info("%s: JSON-LD extracted %d listings", self.name, len(results))
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
            if "InStock" in avail_url:
                availability = "in_stock"
            elif "OutOfStock" in avail_url:
                availability = "out_of_stock"
            else:
                availability = "unknown"

            agg = item.get("aggregateRating", {})
            rating = _to_float(agg.get("ratingValue"))
            review_count = _to_int(agg.get("reviewCount"))

            images = item.get("image", [])
            image_url = images[0] if isinstance(images, list) and images else (images if isinstance(images, str) else None)

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
        """Extract product cards from Vijay Sales search results DOM."""
        results = []

        card_selectors = [
            "div.product-card",
            "div.Dynamic-Bucket-item",
            "div.vsp-product-card",
            "div[data-product-id]",
            "div.search-item",
            "div.product-list-item",
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

        logger.info("%s: DOM extracted %d listings", self.name, len(results))
        return results

    def _parse_dom_card(self, card, crawl_id: str) -> Optional[ScrapedListing]:
        try:
            # Title element
            name_el = (
                card.select_one("h2")
                or card.select_one("h3")
                or card.select_one(".product-title")
                or card.select_one(".prdt-title")
                or card.select_one("a[title]")
            )
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                return None

            # Link
            link_el = card.select_one("a[href]")
            href = link_el["href"] if link_el else ""
            product_url = href if href.startswith("http") else self.base_url + href

            # Selling price
            price_el = (
                card.select_one(".offer-price")
                or card.select_one(".selling-price")
                or card.select_one(".final-price")
                or card.select_one(".price")
                or card.select_one(".prdt-price")
            )
            selling = _extract_price(price_el.get_text() if price_el else "")
            if selling is None:
                return None

            # MRP
            mrp_el = (
                card.select_one(".mrp-price")
                or card.select_one(".mrp")
                or card.select_one(".regular-price")
                or card.select_one("strike")
            )
            mrp = _extract_price(mrp_el.get_text() if mrp_el else "")
            discount = round(mrp - selling, 2) if mrp and mrp > selling else None

            # Image
            img_el = card.select_one("img")
            image_url = None
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src") or img_el.get("data-original")

            # Stated offer/EMI text if visible on card
            offer_el = card.select_one(".offer-tag") or card.select_one(".bank-offer") or card.select_one(".emi-text")
            offer_text = offer_el.get_text(strip=True) if offer_el else None

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
                offer_text=offer_text,
                crawl_id=crawl_id,
            )
        except Exception as exc:
            logger.warning("%s: failed to parse DOM card: %s", self.name, exc)
            return None
