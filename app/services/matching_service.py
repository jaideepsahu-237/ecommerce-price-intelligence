"""Product matching and normalization service.

Takes raw listings across multiple retailers and generates canonical
product identity and variant_id slugs to match equivalent products
(e.g., iPhone 17 Pro 256GB Black on Croma == iPhone 17 Pro 256GB Black on Vijay Sales).
"""

import difflib
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
    "honor": "Honor",
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


_ACCESSORY_RE = re.compile(
    r"\b("
    r"cases?|covers?|bumper|pouch|sleeve|wallet|skin|strap|band|"
    r"tempered\s*glass|screen\s*(?:guard|protector)|(?:camera|lens)\s*protector|"
    r"chargers?|adapters?|cables?|power\s*banks?|earphones?|earbuds?|headphones?|"
    r"holders?|stands?|tripods?|stylus|magsafe\s*(?:case|wallet|charger|stand)"
    r")\b",
    re.IGNORECASE,
)


def is_accessory(product_name: str, selling_price: float = 0.0) -> bool:
    """Return True if a listing looks like a phone accessory rather than a smartphone."""
    if selling_price and 0 < selling_price < 3000:
        return True
    return bool(product_name and _ACCESSORY_RE.search(product_name))


def correct_brand_typos(query: str) -> str:
    """Detect and autocorrect common brand typos in search queries (e.g. Samanung -> Samsung)."""
    words = query.strip().split()
    corrected = []
    brand_keys = list(_CANONICAL_BRANDS.keys())

    for word in words:
        clean = re.sub(r"[^\w]", "", word.lower())
        matches = difflib.get_close_matches(clean, brand_keys, n=1, cutoff=0.72)
        if matches:
            canonical = _CANONICAL_BRANDS[matches[0]]
            corrected.append(canonical)
        else:
            corrected.append(word)

    return " ".join(corrected)



def normalize_brand(brand_raw: Optional[str], title: str) -> str:
    """Normalize brand name to canonical casing."""
    if isinstance(brand_raw, list):
        brand_raw = brand_raw[0] if brand_raw else ""
    text = str(brand_raw or "").strip().lower()
    if text in _CANONICAL_BRANDS:
        return _CANONICAL_BRANDS[text]

    # Search in title
    title_lower = title.lower()
    for key, val in _CANONICAL_BRANDS.items():
        if re.search(rf"\b{re.escape(key)}\b", title_lower):
            return val

    return (brand_raw or "Generic").strip().title()


def normalize_storage(storage_raw: Optional[str], title: str) -> Optional[str]:
    """Normalize storage to '128 GB', '256 GB', '512 GB', '1 TB' (ignoring RAM like 8GB/12GB)."""
    fallback = None
    for text in (storage_raw, title):
        if not text:
            continue
        matches = re.findall(r"\b(\d+)\s*([GT]B)\b", text, re.IGNORECASE)
        if not matches:
            continue
        # Prefer TB or >= 32 GB so RAM sizes (8GB, 12GB, 16GB) are not mistaken for storage
        candidates = [
            (int(num), unit.upper())
            for num, unit in matches
            if unit.upper() == "TB" or int(num) >= 32
        ]
        if candidates:
            num, unit = max(candidates, key=lambda x: x[0] * (1024 if x[1] == "TB" else 1))
            return f"{num} {unit}"
        if fallback is None:
            fallback = f"{matches[0][0]} {matches[0][1].upper()}"
    return fallback


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

    def listing_record_to_scraped(self, product, listing) -> ScrapedListing:
        """Convert a database ProductListing record back to a ScrapedListing."""
        return ScrapedListing(
            product_name=listing.product_name,
            product_url=listing.product_url,
            source=listing.retailer.slug if listing.retailer else "database",
            selling_price=float(listing.selling_price) if listing.selling_price else 0.0,
            brand=product.brand,
            model=product.model,
            storage=product.storage,
            colour=product.colour,
            image_url=listing.image_url,
            mrp=float(listing.mrp) if listing.mrp else None,
            discount=float(listing.discount) if listing.discount else None,
            availability=listing.availability,
            offer_text=listing.offer_text,
            crawl_id=listing.crawl_id or "cached",
        )
