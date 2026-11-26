"""Product matching and normalization service.

Takes raw listings across multiple retailers and generates canonical
product identity and variant_id slugs to match equivalent products
(e.g., iPhone 17 Pro 256GB Black on Croma == iPhone 17 Pro 256GB Black on Vijay Sales).
"""

import re
from typing import Optional
from app.scrapers.base import ScrapedListing

_CANONICAL_BRANDS = {
    "apple": "Apple",
    "samsung": "Samsung",
    "oneplus": "OnePlus",
    "google": "Google",
    "xiaomi": "Xiaomi",
    "redmi": "Redmi",
    "poco": "Poco",
    "realme": "Realme",
    "oppo": "Oppo",
    "vivo": "Vivo",
    "motorola": "Motorola",
    "moto": "Motorola",
    "iqoo": "iQOO",
    "nothing": "Nothing",
}

_COLOUR_ALIASES = {
    "space grey": "Space Grey",
    "space gray": "Space Grey",
    "natural titanium": "Natural Titanium",
    "desert titanium": "Desert Titanium",
    "white titanium": "White Titanium",
    "black titanium": "Black Titanium",
    "phantom black": "Black",
    "midnight": "Black",
    "starlight": "White",
    "sky blue": "Blue",
}


def normalize_brand(brand_raw: Optional[str], title: str) -> str:
    """Normalize brand name to canonical casing."""
    text = (brand_raw or "").strip().lower()
    if text in _CANONICAL_BRANDS:
        return _CANONICAL_BRANDS[text]

    # Search in title
    title_lower = title.lower()
    for key, val in _CANONICAL_BRANDS.items():
        if re.search(rf"\b{re.escape(key)}\b", title_lower):
            return val

    return (brand_raw or "Generic").strip().title()


def normalize_storage(storage_raw: Optional[str], title: str) -> Optional[str]:
    """Normalize storage to '128 GB', '256 GB', '512 GB', '1 TB'."""
    text = storage_raw or title
    m = re.search(r"\b(\d+)\s*([GT]B)\b", text, re.IGNORECASE)
    if m:
        num, unit = m.group(1), m.group(2).upper()
        return f"{num} {unit}"
    return None


def normalize_colour(colour_raw: Optional[str]) -> Optional[str]:
    """Normalize colour strings and common aliases."""
    if not colour_raw:
        return None
    cleaned = colour_raw.strip().lower()
    for alias, canonical in _COLOUR_ALIASES.items():
        if alias in cleaned:
            return canonical
    return colour_raw.strip().title()


def slugify(text: str) -> str:
    """Create URL/key safe slug from text."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")


def generate_variant_id(brand: str, model: str, storage: Optional[str], colour: Optional[str]) -> str:
    """Generate a deterministic deduplication key for a product variant.

    Example:
        brand="Apple", model="iPhone 17 Pro", storage="256 GB", colour="Black"
        -> "apple_iphone-17-pro_256-gb_black"
    """
    b_slug = slugify(brand)
    m_slug = slugify(model)
    s_slug = slugify(storage or "unknown-storage")
    c_slug = slugify(colour or "any-colour")
    return f"{b_slug}_{m_slug}_{s_slug}_{c_slug}"


class MatchingService:
    """Normalizes scraped listings and identifies equivalent variants."""

    def normalize_listing(self, listing: ScrapedListing) -> dict:
        """Extract and normalize canonical attributes from a scraped listing."""
        brand = normalize_brand(listing.brand, listing.product_name)
        storage = normalize_storage(listing.storage, listing.product_name)
        colour = normalize_colour(listing.colour)

        # Clean model name
        model = listing.model
        if not model or model.lower() == brand.lower():
            # Extract model by removing brand & storage from title
            m = listing.product_name
            m = re.sub(rf"\b{re.escape(brand)}\b", "", m, flags=re.IGNORECASE)
            if storage:
                m = re.sub(rf"\b{re.escape(storage)}\b", "", m, flags=re.IGNORECASE)
                m = re.sub(rf"\b{re.escape(storage.replace(' ', ''))}\b", "", m, flags=re.IGNORECASE)
            m = re.sub(r"[(),\-]+", " ", m)
            model = re.sub(r"\s+", " ", m).strip()

        variant_id = generate_variant_id(brand, model, storage, colour)

        return {
            "brand": brand,
            "model": model,
            "storage": storage,
            "colour": colour,
            "variant_id": variant_id,
        }
