"""Optional Playwright-based offer enrichment for client-side hydrated PDPs.

Reliance Digital and Vijay Sales load per-SKU bank/card discounts dynamically
via JavaScript. This module selectively opens the top listings in headless
Chromium to extract visible bank offer text without slowing down the whole search.
"""

import logging
import re
from typing import Optional

from app.scrapers.base import ScrapedListing

logger = logging.getLogger(__name__)

_OFFER_PATTERNS = [
    re.compile(
        r"((?:ICICI|HDFC|SBI|Axis|Kotak|IDFC|RBL|HSBC|OneCard|BOB|Amex)"
        r"[^.\n]{0,90}?(?:₹|Rs\.?)\s*[\d,]+[^.\n]{0,40})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(Flat\s*(?:₹|Rs\.?)\s*[\d,]+[^.\n]{0,80}?(?:Bank|Card|EMI)[^.\n]{0,40})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(Best\s*Price\s*[:\-]?\s*(?:₹|Rs\.?)\s*[\d,]+)",
        re.IGNORECASE,
    ),
    re.compile(
        r"((?:ICICI|HDFC|SBI|Axis|Kotak|IDFC|RBL|HSBC|OneCard|BOB|Amex|"
        r"Standard\s*Chartered|Indian\s*Overseas)\s+Bank\s+(?:Credit|Debit)\s+Card"
        r"[^\n]{0,50}?(?:No\s*Cost\s*EMI|Low\s*Cost\s*EMI|Instant\s*Discount|Cashback))",
        re.IGNORECASE,
    ),
]


def _extract_offer_from_text(body_text: str) -> Optional[str]:
    """Collect up to 3 distinct bank/best-price offer snippets from rendered page text."""
    if not body_text:
        return None
    normalized = re.sub(r"[ \t]+", " ", body_text)
    normalized = re.sub(r"Best\s*Price\s*\n+\s*(₹|Rs\.?)", r"Best Price \1", normalized, flags=re.IGNORECASE)

    found: list[str] = []
    seen: set[str] = set()
    for pattern in _OFFER_PATTERNS:
        for m in pattern.finditer(normalized):
            snippet = re.sub(r"\s+", " ", m.group(1)).strip()
            key = snippet.lower()[:50]
            if len(snippet) > 10 and key not in seen:
                seen.add(key)
                found.append(snippet[:140])
                if len(found) >= 3:
                    return " | ".join(found)
    return " | ".join(found) if found else None


def enrich_offers_with_playwright(
    listings: list[ScrapedListing],
    max_per_retailer: int = 5,
    timeout_ms: int = 10000,
) -> list[ScrapedListing]:
    """Enrich top Vijay Sales and Reliance Digital listings with rendered bank offers."""
    if not listings:
        return listings

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.debug("Playwright not installed; skipping dynamic offer enrichment")
        return listings

    # Pick top priced listings per target retailer that lack specific bank offer text
    targets: list[ScrapedListing] = []
    counts: dict[str, int] = {}
    priced = sorted(
        [l for l in listings if l.selling_price and l.selling_price > 0 and l.product_url],
        key=lambda x: x.selling_price,
    )
    for item in priced:
        if item.source not in ("vijay-sales", "reliance-digital"):
            continue
        if counts.get(item.source, 0) >= max_per_retailer:
            continue
        counts[item.source] = counts.get(item.source, 0) + 1
        targets.append(item)

    if not targets:
        return listings

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                )
            )
            page = context.new_page()
            try:
                for item in targets:
                    try:
                        page.goto(item.product_url, wait_until="domcontentloaded", timeout=timeout_ms)
                        try:
                            page.wait_for_selector("text=/Instant Discount|Best Price/i", timeout=3500)
                        except Exception:
                            page.wait_for_timeout(1500)
                        body_text = page.inner_text("body")
                        extracted = _extract_offer_from_text(body_text)
                        if extracted:
                            item.offer_text = extracted
                            logger.info("%s: Playwright extracted offer '%s'", item.source, extracted)
                    except Exception as exc:
                        logger.debug("%s: Playwright enrichment failed for %s: %s", item.source, item.product_url, exc)
            finally:
                browser.close()
    except Exception as exc:
        logger.warning("Playwright browser launch failed; skipping enrichment: %s", exc)

    return listings
