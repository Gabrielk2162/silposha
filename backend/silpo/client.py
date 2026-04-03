"""Wrapper around pysilpo for Silpo API interactions."""

from __future__ import annotations

import httpx

from backend.config import settings

CATALOG_API = "https://api.catalog.ecom.silpo.ua/api/2.0/exec/EcomCatalogGlobal"


async def search_products(
    query: str,
    filial_id: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    """Search products in Silpo catalog (no auth required)."""
    payload = {
        "method": "GetSimpleCatalogItems",
        "data": {
            "customFilter": query,
            "filialId": filial_id or settings.silpo_default_filial_id,
            "skuPerPage": per_page,
            "pageNumber": page,
        },
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(CATALOG_API, json=payload)
        resp.raise_for_status()
        return resp.json()


async def get_product_details(product_id: str, filial_id: str | None = None) -> dict:
    """Get details for a specific product."""
    payload = {
        "method": "GetSimpleCatalogItems",
        "data": {
            "skuIds": [product_id],
            "filialId": filial_id or settings.silpo_default_filial_id,
        },
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(CATALOG_API, json=payload)
        resp.raise_for_status()
        return resp.json()


async def get_categories(filial_id: str | None = None) -> dict:
    """Get product categories."""
    payload = {
        "method": "GetCategories",
        "data": {
            "filialId": filial_id or settings.silpo_default_filial_id,
        },
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(CATALOG_API, json=payload)
        resp.raise_for_status()
        return resp.json()
