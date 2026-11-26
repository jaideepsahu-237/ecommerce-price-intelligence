"""Base scraper adapter and shared data contract.

Every retailer adapter subclasses BaseScraper and returns a list of
ScrapedListing objects. The rest of the app never touches raw HTML —
it only works with ScrapedListing instances.
"""

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalized output contract
# ---------------------------------------------------------------------------

@dataclass
class ScrapedListing:
    """One product listing as scraped from a single retailer page.

    Every adapter must map its retailer-specific fields into this shape.
    Leave fields as None when the source doesn't expose them — never invent
    prices, offers, or stock status.
    """

    # Required
    product_name: str
    product_url: str
    source: str                        # retailer slug, e.g. "croma"
    selling_price: float

    # Product identity (filled by scraper or later by matching service)
    brand: Optional[str] = None
    model: Optional[str] = None
    storage: Optional[str] = None
    colour: Optional[str] = None
    sku: Optional[str] = None

    # Page data
    image_url: Optional[str] = None
    currency: str = "INR"
    mrp: Optional[float] = None
    discount: Optional[float] = None
    availability: str = "unknown"
    seller: Optional[str] = None
    rating: Optional[float] = None
    review_count: Optional[int] = None

    # Offers — raw text as the retailer shows it
    offer_text: Optional[str] = None
    offer_type: Optional[str] = None
    bank: Optional[str] = None
    offer_discount: Optional[float] = None

    # EMI info stated by the retailer (not our calculation)
    emi_available: Optional[bool] = None
    emi_tenure: Optional[int] = None
    emi_rate: Optional[float] = None
    emi_monthly: Optional[float] = None

    # Scrape metadata
    scraped_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    crawl_id: str = ""


# ---------------------------------------------------------------------------
# Base adapter
# ---------------------------------------------------------------------------

class BaseScraper(ABC):
    """Abstract base for all retailer scrapers.

    Subclasses set `name`, `base_url` and implement `search()`.
    The base class handles sessions, throttling, timeouts, and logging.
    """

    name: str = ""
    base_url: str = ""
    request_interval: float = 2.0   # min seconds between requests to this host
    timeout: int = 15               # request timeout in seconds
    max_retries: int = 2            # retries for transient (5xx / timeout) errors

    def __init__(self, base_url: Optional[str] = None):
        if base_url:
            self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-IN,en;q=0.9",
        })
        self._last_request_at = 0.0

    # --- HTTP helpers -----------------------------------------------------

    def _throttle(self):
        """Wait if needed to respect per-host request interval."""
        elapsed = time.time() - self._last_request_at
        wait = self.request_interval - elapsed
        if wait > 0:
            logger.debug("%s: throttling %.1fs", self.name, wait)
            time.sleep(wait)

    def _get(self, url: str, **kwargs) -> requests.Response:
        """Throttled GET with retries for transient failures."""
        kwargs.setdefault("timeout", self.timeout)
        last_exc = None

        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            self._last_request_at = time.time()
            try:
                resp = self.session.get(url, **kwargs)

                # Don't retry client errors (403, 404) — they won't fix themselves
                if resp.status_code in (403, 404, 429):
                    logger.warning(
                        "%s: %s returned %s — not retrying", self.name, url, resp.status_code
                    )
                    resp.raise_for_status()

                resp.raise_for_status()
                return resp

            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                logger.warning("%s: connection error (attempt %d/%d): %s",
                               self.name, attempt, self.max_retries, exc)
            except requests.exceptions.Timeout as exc:
                last_exc = exc
                logger.warning("%s: timeout (attempt %d/%d): %s",
                               self.name, attempt, self.max_retries, exc)
            except requests.exceptions.HTTPError as exc:
                if exc.response is not None and exc.response.status_code >= 500:
                    last_exc = exc
                    logger.warning("%s: server error %s (attempt %d/%d)",
                                   self.name, exc.response.status_code,
                                   attempt, self.max_retries)
                else:
                    raise  # 4xx — don't retry

            # Back off before next retry
            if attempt < self.max_retries:
                backoff = self.request_interval * attempt
                logger.debug("%s: backing off %.1fs", self.name, backoff)
                time.sleep(backoff)

        # All retries exhausted
        raise requests.exceptions.ConnectionError(
            f"{self.name}: all {self.max_retries} attempts failed for {url}"
        ) from last_exc

    # --- Crawl ID ---------------------------------------------------------

    def _make_crawl_id(self) -> str:
        return f"{self.name}-{uuid.uuid4().hex[:8]}"

    # --- Interface --------------------------------------------------------

    @abstractmethod
    def search(self, query: str, **filters) -> list[ScrapedListing]:
        """Search for products matching the query.

        Args:
            query: search string, e.g. "iPhone 17 Pro"
            **filters: optional filters like storage="256 GB", colour="Black"

        Returns:
            List of ScrapedListing objects. May be empty if the source has
            no results or is unreachable.
        """
        ...
