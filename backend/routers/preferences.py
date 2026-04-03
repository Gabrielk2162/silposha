from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.engine.analyzer import get_purchase_stats
from backend.models import Preference, PurchaseHistory, User
from datetime import datetime

router = APIRouter(prefix="/preferences", tags=["preferences"])


class PreferenceCreate(BaseModel):
    category: str  # brand, diet, allergy, budget, frequency, blacklist, whitelist
    key: str
    value: str


class PurchaseCreate(BaseModel):
    product_name: str
    product_id: str | None = None
    category: str | None = None
    brand: str | None = None
    price: float | None = None
    quantity: int = 1
    purchased_at: str | None = None  # ISO format


@router.get("/{user_id}")
async def get_preferences(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Preference).where(Preference.user_id == user_id))
    prefs = result.scalars().all()
    return [
        {"id": p.id, "category": p.category, "key": p.key, "value": p.value}
        for p in prefs
    ]


@router.post("/{user_id}")
async def add_preference(user_id: int, body: PreferenceCreate, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    pref = Preference(user_id=user_id, category=body.category, key=body.key, value=body.value)
    db.add(pref)
    await db.commit()
    await db.refresh(pref)
    return {"id": pref.id, "category": pref.category, "key": pref.key, "value": pref.value}


@router.delete("/{preference_id}")
async def delete_preference(preference_id: int, db: AsyncSession = Depends(get_db)):
    pref = await db.get(Preference, preference_id)
    if not pref:
        raise HTTPException(404, "Preference not found")
    await db.delete(pref)
    await db.commit()
    return {"deleted": preference_id}


@router.post("/{user_id}/purchases")
async def add_purchase(user_id: int, body: PurchaseCreate, db: AsyncSession = Depends(get_db)):
    """Manually add a purchase to history."""
    purchased_at = datetime.fromisoformat(body.purchased_at) if body.purchased_at else datetime.utcnow()
    purchase = PurchaseHistory(
        user_id=user_id,
        product_name=body.product_name,
        product_id=body.product_id,
        category=body.category,
        brand=body.brand,
        price=body.price,
        quantity=body.quantity,
        purchased_at=purchased_at,
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)
    return {"id": purchase.id, "product": purchase.product_name}


@router.get("/{user_id}/stats")
async def get_stats(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get purchase analytics for a user."""
    return await get_purchase_stats(db, user_id)
