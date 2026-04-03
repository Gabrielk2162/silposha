"""Purchase history analyzer.

Analyzes past purchases to find patterns: frequency, preferred brands,
typical quantities, and seasonal trends.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import PurchaseHistory


async def get_purchase_stats(db: AsyncSession, user_id: int) -> dict:
    """Analyze purchase history and return structured stats."""
    result = await db.execute(
        select(PurchaseHistory)
        .where(PurchaseHistory.user_id == user_id)
        .order_by(PurchaseHistory.purchased_at.desc())
    )
    purchases = result.scalars().all()

    if not purchases:
        return {"total_purchases": 0, "frequent_items": [], "brand_preferences": {}, "purchase_patterns": []}

    # Frequency analysis: how often each product is bought
    product_dates: dict[str, list[datetime]] = defaultdict(list)
    product_counts = Counter()
    brand_counts = Counter()
    category_counts = Counter()

    for p in purchases:
        product_dates[p.product_name].append(p.purchased_at)
        product_counts[p.product_name] += p.quantity
        if p.brand:
            brand_counts[p.brand] += 1
        if p.category:
            category_counts[p.category] += 1

    # Calculate average interval between purchases for each product
    purchase_patterns = []
    for product_name, dates in product_dates.items():
        if len(dates) >= 2:
            sorted_dates = sorted(dates)
            intervals = [
                (sorted_dates[i + 1] - sorted_dates[i]).days for i in range(len(sorted_dates) - 1)
            ]
            avg_interval = sum(intervals) / len(intervals)
            last_purchase = sorted_dates[-1]
            days_since_last = (datetime.utcnow() - last_purchase).days

            purchase_patterns.append({
                "product": product_name,
                "avg_interval_days": round(avg_interval, 1),
                "days_since_last": days_since_last,
                "total_purchased": product_counts[product_name],
                "times_bought": len(dates),
                "due": days_since_last >= avg_interval,
            })

    # Sort: items that are "due" first, then by frequency
    purchase_patterns.sort(key=lambda x: (-x["due"], -x["times_bought"]))

    return {
        "total_purchases": len(purchases),
        "frequent_items": product_counts.most_common(20),
        "brand_preferences": dict(brand_counts.most_common(10)),
        "category_preferences": dict(category_counts.most_common(10)),
        "purchase_patterns": purchase_patterns,
    }


async def get_items_due_for_reorder(db: AsyncSession, user_id: int) -> list[dict]:
    """Get items that are likely needed based on purchase frequency."""
    stats = await get_purchase_stats(db, user_id)
    return [p for p in stats["purchase_patterns"] if p["due"]]
