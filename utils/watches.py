from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

import cloudscraper
from bs4 import BeautifulSoup

logger = logging.getLogger("drophunter.watches")

_ALLOWED_HOST = "swisstimehouse.com"


def _is_swisstimehouse(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host == _ALLOWED_HOST or host.endswith("." + _ALLOWED_HOST)


def _extract_product_jsonld(html: str) -> dict | None:
    """Return the first schema.org Product JSON-LD object with a price, or None."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text() or ""
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for obj in candidates:
            if not isinstance(obj, dict):
                continue
            if obj.get("@type") != "Product":
                continue
            offers = obj.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if offers.get("price") is None:
                continue
            return obj
    return None


def fetch_swisstimehouse(url: str) -> dict | None:
    """
    Fetch a swisstimehouse.com product page and parse its schema.org JSON-LD.
    Returns {name, brand, reference, price} or None on any failure.
    """
    if not _is_swisstimehouse(url):
        logger.warning("Rejecting non-swisstimehouse URL: %s", url)
        return None

    try:
        scraper = cloudscraper.create_scraper()
        response = scraper.get(url, timeout=30)
        response.raise_for_status()
        html = response.text
    except Exception as exc:
        logger.warning("Failed to fetch swisstimehouse URL %s: %s", url, exc)
        return None

    product = _extract_product_jsonld(html)
    if product is None:
        logger.warning("No Product JSON-LD with a price found at %s", url)
        return None

    offers = product.get("offers") or {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    brand = product.get("brand") or {}
    brand_name = brand.get("name") if isinstance(brand, dict) else brand

    result = {
        "name": product.get("name"),
        "brand": brand_name,
        "reference": product.get("sku") or product.get("mpn"),
        "price": float(offers["price"]),
    }
    logger.info(
        "Fetched %s: %s (ref=%s) ₹%.2f",
        url,
        result["name"],
        result["reference"],
        result["price"],
    )
    return result
