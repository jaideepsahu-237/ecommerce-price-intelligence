"""Croma scraper adapter.

Primary approach: hit Croma's search API (api.croma.com/searchservices)
which returns structured JSON with product names, prices, ratings, stock.

Fallback: fetch the category/search HTML page and extract product data
from embedded JSON-LD (<script type="application/ld+json">) blocks or
DOM elements.

Both approaches may be blocked by Croma's WAF. When that happens the
scraper logs a warning and returns an empty list — it never crashes the
search service.
"""

import json
import logging
import re
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.config import Config
from app.scrapers.base import BaseScraper, ScrapedListing

logger = logging.getLogger(__name__)


class CromaScraper(BaseScraper):

    name = "croma"
    base_url = Config.CROMA_BASE_URL
    api_url = Config.CROMA_API_URL
    request_interval = 2.5  # be conservative with Croma

    def __init__(self, base_url: Optional[str] = None, api_url: Optional[str] = None):
        super().__init__(base_url=base_url or Config.CROMA_BASE_URL)
        self.api_url = api_url or Config.CROMA_API_URL

    # Croma search API path (observed from browser network tab)
    SEARCH_PATH = "/searchservices/v1/search"

    # Category URL for iPhones (from the technical test doc)
    IPHONE_CATEGORY = "/phones-wearables/mobile-phones/apple-iphones/c/97"

    def search(self, query: str, **filters) -> list[ScrapedListing]:
        """Search Croma for smartphones matching the query."""
        crawl_id = self._make_crawl_id()
        logger.info("%s: searching for '%s'", self.name, query)

        # Try the structured API first
        listings = self._search_via_api(query, crawl_id, **filters)
        if listings:
            return listings

        # Fallback: scrape the HTML search page
        logger.info("%s: API unavailable, falling back to HTML scrape", self.name)
        return self._search_via_html(query, crawl_id, **filters)

    # ------------------------------------------------------------------
    # Approach 1: Search API
    # ------------------------------------------------------------------

    def _search_via_api(self, query: str, crawl_id: str, **filters) -> list[ScrapedListing]:
        url = f"{self.api_url}{self.SEARCH_PATH}"
        params = {
            "searchType": "keyword",
            "text": query,
            "sortBy": "relevance",
            "pageSize": 24,
            "pageNo": 0,
        }

        try:
            resp = self._get(url, params=params)
            data = resp.json()
        except Exception as exc:
            logger.warning("%s: API request failed: %s", self.name, exc)
            return []

        products = (
            data.get("data", {}).get("products")
            or data.get("products")
            or []
        )

        results = []
        for item in products:
            listing = self._parse_api_product(item, crawl_id)
            if listing:
                results.append(listing)

        logger.info("%s: API returned %d listings", self.name, len(results))
        return results

    def _parse_api_product(self, item: dict, crawl_id: str) -> Optional[ScrapedListing]:
        """Parse one product from the API JSON response."""
        try:
            name = item.get("name", "").strip()
            if not name:
                return None

            # Price block — API nests it under "price" or at top level
            price_block = item.get("price", item)
            selling = _to_float(price_block.get("sellingPrice") or price_block.get("selling_price"))
            if selling is None:
                return None

            mrp = _to_float(price_block.get("mrp"))
            discount = round(mrp - selling, 2) if mrp and selling and mrp > selling else None

            # Product URL
            relative_url = item.get("url", "")
            product_url = self.base_url + relative_url if relative_url else ""

            # Stock
            stock_block = item.get("stock", {})
            if isinstance(stock_block, dict):
                available = stock_block.get("isAvailable", stock_block.get("available"))
            else:
                available = None
            availability = "in_stock" if available else ("out_of_stock" if available is False else "unknown")

            # Image
            images = item.get("images", item.get("image", []))
            image_url = images[0] if isinstance(images, list) and images else (images if isinstance(images, str) else None)

            # Ratings
            ratings_block = item.get("ratings", item.get("aggregateRating", {}))
            rating = _to_float(ratings_block.get("averageRating") or ratings_block.get("ratingValue"))
            review_count = _to_int(ratings_block.get("reviewCount"))

            # Brand / storage / colour from name
            brand, model, storage, colour = _parse_product_name(name)

            return ScrapedListing(
                product_name=name,
                product_url=product_url,
                source=self.name,
                selling_price=selling,
                brand=brand or item.get("brand", {}).get("name") if isinstance(item.get("brand"), dict) else item.get("brand"),
                model=model,
                storage=storage,
                colour=colour,
                sku=item.get("sku") or item.get("code"),
                image_url=image_url,
                mrp=mrp,
                discount=discount,
                availability=availability,
                rating=rating,
                review_count=review_count,
                crawl_id=crawl_id,
            )
        except Exception as exc:
            logger.warning("%s: failed to parse API product: %s", self.name, exc)
            return None

    # ------------------------------------------------------------------
    # Approach 2: HTML scrape with JSON-LD / DOM parsing
    # ------------------------------------------------------------------

    def _search_via_html(self, query: str, crawl_id: str, **filters) -> list[ScrapedListing]:
        search_url = f"{self.base_url}/search/?text={quote_plus(query)}"

        try:
            resp = self._get(search_url)
        except Exception as exc:
            logger.warning("%s: HTML request failed: %s", self.name, exc)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try JSON-LD blocks first (cleanest structured data)
        results = self._extract_jsonld(soup, crawl_id)
        if results:
            return results

        # Fall back to DOM elements
        return self._extract_dom(soup, crawl_id)

    def _extract_jsonld(self, soup: BeautifulSoup, crawl_id: str) -> list[ScrapedListing]:
        """Pull product data from <script type="application/ld+json"> tags."""
        results = []
        for script_tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script_tag.string or "")
            except (json.JSONDecodeError, TypeError):
                continue

            # Could be a single product or a list
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") != "Product":
                    continue
                listing = self._parse_jsonld_product(item, crawl_id)
                if listing:
                    results.append(listing)

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

            product_url = offers.get("url", "")
            if product_url and not product_url.startswith("http"):
                product_url = self.base_url + product_url

            # Availability from schema.org URL
            avail_url = offers.get("availability", "")
            if "InStock" in avail_url:
                availability = "in_stock"
            elif "OutOfStock" in avail_url:
                availability = "out_of_stock"
            else:
                availability = "unknown"

            # Ratings
            agg = item.get("aggregateRating", {})
            rating = _to_float(agg.get("ratingValue"))
            review_count = _to_int(agg.get("reviewCount"))

            # Images
            images = item.get("image", [])
            image_url = images[0] if isinstance(images, list) and images else (images if isinstance(images, str) else None)

            brand_data = item.get("brand", {})
            brand_name = brand_data.get("name") if isinstance(brand_data, dict) else brand_data
            brand, model, storage, colour = _parse_product_name(name)

            return ScrapedListing(
                product_name=name,
                product_url=product_url,
                source=self.name,
                selling_price=selling,
                brand=brand or brand_name,
                model=model,
                storage=storage,
                colour=colour,
                sku=item.get("sku"),
                image_url=image_url,
                mrp=None,  # JSON-LD usually only has the selling price
                availability=availability,
                rating=rating,
                review_count=review_count,
                crawl_id=crawl_id,
            )
        except Exception as exc:
            logger.warning("%s: failed to parse JSON-LD product: %s", self.name, exc)
            return None

    def _extract_dom(self, soup: BeautifulSoup, crawl_id: str) -> list[ScrapedListing]:
        """Last resort: parse product cards from the HTML DOM.

        Croma's CSS classes change over time, so this may need updating.
        Common patterns observed: product cards in <li> or <div> with
        classes like 'product-item', 'plp-prod-item', 'product-card'.
        """
        results = []

        # Try several known card selectors — the first one that finds
        # elements wins
        card_selectors = [
            "li.product-item",
            "div.product-card",
            "div[data-testid='product']",
            "div.plp-prod-item",
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
            # Product name from heading or link text
            name_el = (
                card.select_one("h3")
                or card.select_one("h2")
                or card.select_one("a[title]")
            )
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                return None

            # Link
            link_el = card.select_one("a[href]")
            href = link_el["href"] if link_el else ""
            product_url = href if href.startswith("http") else self.base_url + href

            # Price — look for common price element patterns
            price_el = (
                card.select_one("[data-testid='selling-price']")
                or card.select_one(".pdpPrice")
                or card.select_one(".new-price")
                or card.select_one(".amount")
            )
            selling = _extract_price(price_el.get_text() if price_el else "")
            if selling is None:
                return None

            # MRP
            mrp_el = card.select_one(".old-price") or card.select_one(".mrp")
            mrp = _extract_price(mrp_el.get_text() if mrp_el else "")
            discount = round(mrp - selling, 2) if mrp and mrp > selling else None

            # Image
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


# ======================================================================
# Helper functions (module-private)
# ======================================================================

def _to_float(value) -> Optional[float]:
    """Safely convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace("₹", "").strip())
    except (ValueError, TypeError):
        return None


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (ValueError, TypeError):
        return None


def _extract_price(text: str) -> Optional[float]:
    """Pull a numeric price out of text like '₹1,29,490' or 'Rs. 129490'."""
    if not text:
        return None
    # Strip currency symbols and prefixes first, then commas
    text = re.sub(r"(?i)^[₹Rs.\s]+", "", text.strip())
    text = text.replace(",", "")
    # Find the first number (integer or decimal)
    match = re.search(r"\d+(?:\.\d+)?", text)
    return float(match.group()) if match else None


# Common brand prefixes to help split "Apple iPhone 17 Pro 256 GB Black"
_KNOWN_BRANDS = {
    "apple", "samsung", "oneplus", "google", "xiaomi", "redmi", "poco",
    "realme", "oppo", "vivo", "motorola", "nokia", "nothing", "iqoo",
    "honor", "huawei", "asus", "sony", "lg",
}

# Regex for storage like "256 GB", "256GB", "1 TB", "1TB"
_STORAGE_RE = re.compile(r"\b(\d+\s*[GT]B)\b", re.IGNORECASE)

# Common colour names
_COLOUR_RE = re.compile(
    r"\b(black|white|blue|green|red|pink|purple|gold|silver|grey|gray|"
    r"titanium|graphite|midnight|starlight|desert|natural|teal|coral|"
    r"lavender|cream|phantom|marble|yellow|orange|aqua|mint|sand|"
    r"bronze|copper|ivory|violet|rose|sky|sage|lime|indigo|slate|"
    r"dark\s+\w+|light\s+\w+)\b",
    re.IGNORECASE,
)


def _parse_product_name(name: str) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Best-effort extraction of brand, model, storage, colour from a product title.

    Strategy: use regex to find storage and colour, then remove the matched
    spans from a working copy to isolate the model name. We work on the
    cleaned string instead of using character positions from the original.
    """
    if not name:
        return None, None, None, None

    # Brand — check if first word matches a known brand
    brand = None
    words = name.split()
    if words and words[0].lower() in _KNOWN_BRANDS:
        brand = words[0]

    # Storage — "256 GB", "256GB", "1 TB"
    storage_match = _STORAGE_RE.search(name)
    storage = None
    if storage_match:
        raw = storage_match.group(1).upper()
        storage = re.sub(r"(\d+)\s*([GT]B)", r"\1 \2", raw)  # "256GB" → "256 GB"

    # Colour — grab all colour words that appear after storage (or at the
    # end of the name).  Combine consecutive matches like "Natural Titanium".
    colour = None
    colour_search_text = name
    if storage_match:
        colour_search_text = name[storage_match.end():]
    colour_matches = list(_COLOUR_RE.finditer(colour_search_text))
    if colour_matches:
        # Join all matched colour fragments: "Natural Titanium", "Phantom Black"
        colour = " ".join(m.group(0).strip() for m in colour_matches).title()

    # Model — start with the full name, strip out brand, storage, and colour
    model_text = name
    if brand:
        model_text = re.sub(re.escape(brand), "", model_text, count=1, flags=re.IGNORECASE).strip()
    if storage_match:
        model_text = re.sub(re.escape(storage_match.group(0)), "", model_text, count=1).strip()
    if colour_matches:
        # Remove each colour word from the model text
        for m in colour_matches:
            model_text = re.sub(re.escape(m.group(0)), "", model_text, count=1, flags=re.IGNORECASE).strip()
    # Clean up stray parens, commas, dashes, and extra whitespace
    model_text = re.sub(r"[(),]+", " ", model_text)
    model_text = re.sub(r"[-]+$", "", model_text)
    model_text = re.sub(r"\s+", " ", model_text).strip()
    model = model_text or None

    return brand, model, storage, colour
