"""Runner for calling Silposha functions from the terminal.

Usage: python -c "from backend.run import *; run(search('молоко'))"
Or simpler via the helper scripts at the bottom.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from backend.database import async_session, engine
from backend.models import Base, CartSuggestion, Preference, PurchaseHistory, User
from backend.silpo.client import search_products, get_product_details, get_categories
from backend.engine.analyzer import get_purchase_stats, get_items_due_for_reorder
from backend.engine.cart_builder import build_smart_cart
from backend.silpo.cart import get_cart as _get_cart, add_by_query as _add_by_query, add_to_cart as _add_to_cart, remove_from_cart as _remove_from_cart, clear_cart as _clear_cart, search_products as _search_silpo
from backend.silpo.browser import get_page, close as close_browser

AUTH_FILE = Path(__file__).resolve().parent.parent / ".silpo_auth.json"


def get_auth_token() -> str | None:
    """Load saved Silpo access token."""
    if AUTH_FILE.exists():
        data = json.loads(AUTH_FILE.read_text())
        return data.get("access_token")
    return None


def run(coro):
    """Run an async function and pretty-print the result."""
    result = asyncio.run(coro)
    if isinstance(result, (dict, list)):
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(result)
    return result


# ── Product search ──

async def search(query: str, page: int = 1, limit: int = 10):
    """Search Silpo products."""
    data = await search_products(query, per_page=limit, page=page)
    items = data.get("items", [])
    return [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "price": p.get("price"),
            "old_price": p.get("oldPrice"),
            "unit": p.get("unit"),
            "image": p.get("mainImage"),
            "promo": p.get("promoTitle"),
            "in_stock": (p.get("quantity") or 0) > 0,
        }
        for p in items
    ]


async def categories():
    """Get Silpo product categories."""
    return await get_categories()


# ── User management ──

async def get_or_create_user(phone: str = "local", name: str = "Local User") -> int:
    """Get or create a user, return user_id."""
    async with async_session() as db:
        result = await db.execute(select(User).where(User.phone == phone))
        user = result.scalar_one_or_none()
        if not user:
            user = User(phone=phone, name=name)
            db.add(user)
            await db.commit()
            await db.refresh(user)
        return user.id


# ── Purchase history ──

async def add_purchase(product_name: str, price: float | None = None,
                       brand: str | None = None, category: str | None = None,
                       quantity: int = 1, product_id: str | None = None,
                       phone: str = "local"):
    """Record a purchase to history."""
    user_id = await get_or_create_user(phone)
    async with async_session() as db:
        purchase = PurchaseHistory(
            user_id=user_id,
            product_name=product_name,
            product_id=product_id,
            category=category,
            brand=brand,
            price=price,
            quantity=quantity,
            purchased_at=datetime.utcnow(),
        )
        db.add(purchase)
        await db.commit()
        return {"status": "ok", "product": product_name, "price": price}


async def history(phone: str = "local", limit: int = 30):
    """Show purchase history."""
    user_id = await get_or_create_user(phone)
    async with async_session() as db:
        result = await db.execute(
            select(PurchaseHistory)
            .where(PurchaseHistory.user_id == user_id)
            .order_by(PurchaseHistory.purchased_at.desc())
            .limit(limit)
        )
        purchases = result.scalars().all()
        return [
            {
                "product": p.product_name,
                "price": p.price,
                "brand": p.brand,
                "category": p.category,
                "qty": p.quantity,
                "date": p.purchased_at.isoformat(),
            }
            for p in purchases
        ]


async def stats(phone: str = "local"):
    """Get purchase statistics."""
    user_id = await get_or_create_user(phone)
    async with async_session() as db:
        return await get_purchase_stats(db, user_id)


async def due(phone: str = "local"):
    """Get items due for reorder."""
    user_id = await get_or_create_user(phone)
    async with async_session() as db:
        return await get_items_due_for_reorder(db, user_id)


# ── Preferences ──

async def set_pref(category: str, key: str, value: str, phone: str = "local"):
    """Set a user preference. Categories: brand, diet, allergy, budget, frequency."""
    user_id = await get_or_create_user(phone)
    async with async_session() as db:
        # Update existing or create new
        result = await db.execute(
            select(Preference).where(
                Preference.user_id == user_id,
                Preference.category == category,
                Preference.key == key,
            )
        )
        pref = result.scalar_one_or_none()
        if pref:
            pref.value = value
        else:
            pref = Preference(user_id=user_id, category=category, key=key, value=value)
            db.add(pref)
        await db.commit()
        return {"status": "ok", "category": category, "key": key, "value": value}


async def prefs(phone: str = "local"):
    """Show all user preferences."""
    user_id = await get_or_create_user(phone)
    async with async_session() as db:
        result = await db.execute(
            select(Preference).where(Preference.user_id == user_id)
        )
        return [
            {"category": p.category, "key": p.key, "value": p.value}
            for p in result.scalars().all()
        ]


# ── Smart cart ──

async def cart(phone: str = "local"):
    """Build a smart cart recommendation."""
    user_id = await get_or_create_user(phone)
    async with async_session() as db:
        return await build_smart_cart(db, user_id)


# ── Silpo browser cart (real site) ──

async def silpo_cart():
    """Get current Silpo cart contents via API."""
    return await _get_cart()


async def silpo_add(query: str, qty: int = 1):
    """Add a product to Silpo cart by search query."""
    return await _add_by_query(query, qty)


async def silpo_remove(order_item_id: str):
    """Remove a product from Silpo cart."""
    return await _remove_from_cart(order_item_id)


async def silpo_clear():
    """Clear Silpo cart."""
    return await _clear_cart()


async def silpo_search(query: str, limit: int = 5):
    """Search products on Silpo."""
    return await _search_silpo(query, limit)


# ── DB init ──

async def init_db():
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return "DB initialized"
