"""Poorvika scraper adapter.

Searches Poorvika via its SSR search endpoint (/s?q=<query>) and extracts
product cards from the rendered HTML DOM.
"""

import logging
import re
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, ScrapedListing
from app.scrapers.croma import _extract_price, _parse_product_name

logger = logging.getLogger(__name__)


class PoorvikaScraper(BaseScraper):

    name = "poorvika"
    base_url = "https://www.poorvika.com"
    request_interval = 2.0

    def __init__(self, base_url: Optional[str] = None):
        super().__init__(base_url=base_url or "https://www.poorvika.com")

    def search(self, query: str, **filters) -> list[ScrapedListing]:
        """Search Poorvika via SSR /s?q= HTML page."""
        if not query:
            return []

        crawl_id = self._make_crawl_id()
        search_url = f"{self.base_url}/s?q={quote_plus(query)}"
        logger.info("%s: searching for '%s'", self.name, query)

        try:
            resp = self._get(search_url)
            if resp.status_code != 200:
                return []
        except Exception as exc:
            logger.warning("%s: search request failed: %s", self.name, exc)
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        cards = soup.select('[class*="product-cardlist_card--border"]')
        if not cards:
            cards = soup.select('[class*="product-cardlist_card__"]')

        listings = []
        for card in cards:
            listing = self._parse_dom_card(card, crawl_id)
            if listing:
                listings.append(listing)

        q_terms = re.sub(r"[^\w\s]", "", query.lower()).split()
        results = [
            l for l in listings
            if all(term in re.sub(r"[^\w\s]", "", l.product_name.lower()) for term in q_terms)
        ]
        logger.info("%s: extracted %d listings for '%s'", self.name, len(results), query)
        return results

    def _parse_dom_card(self, card, crawl_id: str) -> Optional[ScrapedListing]:
        try:
            name_el = (
                card.select_one('[class*="product-cardlist_card__description"] a b')
                or card.select_one('[class*="product-cardlist_card__description"] a')
            )
            name = name_el.get_text(strip=True) if name_el else ""
            if not name:
                return None

            link_el = (
                card.select_one('[class*="product-cardlist_card__description"] a[href]')
                or card.select_one("a.m-auto[href]")
                or card.select_one("a[href]")
            )
            href = link_el["href"] if link_el else ""
            product_url = href if href.startswith("http") else f"{self.base_url}{href}"

            price_el = (
                card.select_one('[class*="product-cardlist_price"] > span.ml-1')
                or card.select_one('[class*="product-cardlist_price"]')
            )
            selling = _extract_price(price_el.get_text() if price_el else "")
            if selling is None:
                return None

            mrp_el = card.select_one('[class*="product-cardlist_savings"] s')
            mrp = _extract_price(mrp_el.get_text() if mrp_el else "")
            discount = round(mrp - selling, 2) if mrp and mrp > selling else None

            img_el = card.select_one("a.m-auto img") or card.select_one("img")
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
