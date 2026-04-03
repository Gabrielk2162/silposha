"""Cart builder: combines AI recommendations with Silpo product search."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.engine.analyzer import get_items_due_for_reorder, get_purchase_stats
from backend.engine.recommender import generate_cart_recommendation
from backend.models import Preference
from backend.silpo.client import search_products

from sqlalchemy import select


async def build_smart_cart(db: AsyncSession, user_id: int) -> dict:
    """Build a complete smart cart suggestion for a user.

    1. Analyze purchase history
    2. Get AI recommendations
    3. Match recommendations to actual Silpo products
    4. Return enriched cart with prices and product IDs
    """
    # Step 1: Analyze history
    stats = await get_purchase_stats(db, user_id)
    due_items = await get_items_due_for_reorder(db, user_id)

    # Step 2: Get user preferences
    prefs_result = await db.execute(
        select(Preference).where(Preference.user_id == user_id)
    )
    prefs = [
        {"category": p.category, "key": p.key, "value": p.value}
        for p in prefs_result.scalars().all()
    ]

    # Step 3: Get AI recommendation
    recommendation = await generate_cart_recommendation(stats, prefs, due_items)

    # Step 4: Match to real Silpo products
    cart_items = []
    total = 0.0

    for item in recommendation.get("items", []):
        try:
            search_result = await search_products(item["name"], per_page=3)
            products = search_result.get("items", [])
            if products:
                product = products[0]  # Best match
                price = product.get("price", 0)
                qty = item.get("quantity", 1)
                cart_items.append({
                    "product_id": product.get("id"),
                    "name": product.get("name", item["name"]),
                    "price": price,
                    "quantity": qty,
                    "image": product.get("mainImage"),
                    "reason": item.get("reason", ""),
                    "matched": True,
                })
                total += price * qty
            else:
                cart_items.append({
                    "product_id": None,
                    "name": item["name"],
                    "price": None,
                    "quantity": item.get("quantity", 1),
                    "reason": item.get("reason", ""),
                    "matched": False,
                })
        except Exception:
            cart_items.append({
                "product_id": None,
                "name": item["name"],
                "price": None,
                "quantity": item.get("quantity", 1),
                "reason": item.get("reason", ""),
                "matched": False,
            })

    return {
        "items": cart_items,
        "total_estimate": round(total, 2),
        "reasoning": recommendation.get("reasoning", ""),
        "stats": {
            "total_history": stats["total_purchases"],
            "due_items": len(due_items),
            "matched_products": sum(1 for i in cart_items if i["matched"]),
        },
    }
