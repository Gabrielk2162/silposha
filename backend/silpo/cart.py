"""Silpo cart operations via direct API.

Uses sf-ecom-api.silpo.ua — no browser needed for cart ops.
Token auto-refreshes via browser when expiring.
"""

from __future__ import annotations

import json
from pathlib import Path

from curl_cffi.requests import AsyncSession

from backend.silpo.browser import ensure_fresh_token

LS_FILE = Path(__file__).resolve().parent.parent.parent / ".ls_dump.json"
BASE = "https://sf-ecom-api.silpo.ua"


def _load_ids() -> tuple[str, str, str]:
    """Load basketId, branchId, companyId from saved state."""
    data = json.loads(LS_FILE.read_text()) if LS_FILE.exists() else {}
    basket_id = data.get("basketId", "")
    # These are stable per-store IDs
    branch_id = data.get("branchIdForSlotsSkeleton", "1edb6b53-596c-6d06-b5f0-b5ff7ea46636")
    company_id = "1ec88c5d-a050-669c-8467-570a157f3e31"
    return basket_id, branch_id, company_id


async def _headers() -> dict:
    token = await ensure_fresh_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Origin": "https://silpo.ua",
        "Referer": "https://silpo.ua/",
    }


async def get_cart() -> dict:
    """Get current cart contents."""
    basket_id, _, _ = _load_ids()
    headers = await _headers()

    async with AsyncSession(impersonate="chrome131") as s:
        r = await s.get(
            f"{BASE}/v2/uk/shopping-cart/{basket_id}?strictValidation=false",
            headers=headers, timeout=10,
        )
        data = r.json()

    items = []
    for shipment in data.get("shipments", []):
        for p in shipment.get("products", []):
            pd = p.get("productData", {})
            d = p.get("data", {})
            items.append({
                "id": p.get("productId"),
                "order_item_id": p.get("orderItemId"),
                "title": pd.get("title", "?"),
                "brand": pd.get("brandTitle", ""),
                "ratio": d.get("displayRatio", pd.get("ratio", "")),
                "price": p.get("price"),
                "old_price": d.get("displayOldPrice"),
                "qty": p.get("quantity"),
                "total": p.get("total"),
                "rating": d.get("guestProductRating"),
                "stock": d.get("stock"),
            })

    return {
        "items": items,
        "total": sum(i["total"] or 0 for i in items),
        "count": len(items),
    }


async def search_products(query: str, limit: int = 5) -> list[dict]:
    """Search products via sf-ecom API (returns UUID product IDs)."""
    _, branch_id, _ = _load_ids()
    headers = await _headers()

    async with AsyncSession(impersonate="chrome131") as s:
        r = await s.get(
            f"{BASE}/v1/uk/branches/{branch_id}/products",
            params={"search": query, "limit": limit, "inStock": "true"},
            headers=headers, timeout=10,
        )
        data = r.json()

    return [
        {
            "id": p.get("id"),
            "title": p.get("title", "?"),
            "brand": p.get("brandTitle", ""),
            "price": p.get("displayPrice"),
            "old_price": p.get("displayOldPrice"),
            "ratio": p.get("displayRatio", ""),
            "rating": p.get("guestProductRating"),
            "stock": p.get("stock"),
        }
        for p in data.get("items", [])
    ]


async def add_to_cart(product_id: str, quantity: int = 1) -> dict:
    """Add a product to cart by UUID product ID."""
    basket_id, branch_id, company_id = _load_ids()
    headers = await _headers()

    async with AsyncSession(impersonate="chrome131") as s:
        r = await s.post(
            f"{BASE}/v2/shopping-cart/{basket_id}/products",
            json={"products": [{
                "productId": product_id,
                "quantity": quantity,
                "modifications": [],
                "branchId": branch_id,
                "companyId": company_id,
            }]},
            headers=headers, timeout=10,
        )
    return {"status": r.status_code, "product_id": product_id, "quantity": quantity}


async def remove_from_cart(order_item_id: str) -> dict:
    """Remove a product from cart by orderItemId."""
    basket_id, branch_id, _ = _load_ids()
    headers = await _headers()

    async with AsyncSession(impersonate="chrome131") as s:
        r = await s.post(
            f"{BASE}/v2/shopping-cart/{basket_id}/remove-batch",
            json={"products": [{"orderItemId": order_item_id, "branchId": branch_id}]},
            headers=headers, timeout=10,
        )
    return {"status": r.status_code, "removed": order_item_id}


async def clear_cart() -> dict:
    """Remove all items from cart."""
    basket_id, _, _ = _load_ids()
    headers = await _headers()

    async with AsyncSession(impersonate="chrome131") as s:
        r = await s.post(
            f"{BASE}/v1/shopping-cart/{basket_id}/clear",
            headers=headers, timeout=10,
        )
    return {"status": r.status_code}


async def add_by_query(query: str, quantity: int = 1) -> dict:
    """Search + add first result to cart. Convenience function."""
    products = await search_products(query, limit=3)
    if not products:
        return {"status": "not_found", "query": query}

    p = products[0]
    result = await add_to_cart(p["id"], quantity)
    result["product"] = p["title"]
    result["price"] = p["price"]
    return result
