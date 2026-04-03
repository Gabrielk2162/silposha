from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.engine.cart_builder import build_smart_cart
from backend.models import CartSuggestion, User

router = APIRouter(prefix="/cart", tags=["cart"])


@router.post("/generate/{user_id}")
async def generate_smart_cart(user_id: int, db: AsyncSession = Depends(get_db)):
    """Generate a smart cart suggestion for the user."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")

    result = await build_smart_cart(db, user_id)

    # Save suggestion to DB
    suggestion = CartSuggestion(
        user_id=user_id,
        items=result["items"],
        total_estimate=result["total_estimate"],
        ai_reasoning=result["reasoning"],
    )
    db.add(suggestion)
    await db.commit()
    await db.refresh(suggestion)

    return {"suggestion_id": suggestion.id, **result}


@router.get("/suggestions/{user_id}")
async def get_suggestions(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get all cart suggestions for a user."""
    result = await db.execute(
        select(CartSuggestion)
        .where(CartSuggestion.user_id == user_id)
        .order_by(CartSuggestion.created_at.desc())
        .limit(10)
    )
    suggestions = result.scalars().all()
    return [
        {
            "id": s.id,
            "status": s.status,
            "items": s.items,
            "total_estimate": s.total_estimate,
            "reasoning": s.ai_reasoning,
            "created_at": s.created_at.isoformat(),
        }
        for s in suggestions
    ]


class UpdateStatus(BaseModel):
    status: str  # approved, rejected, ordered


@router.patch("/suggestions/{suggestion_id}")
async def update_suggestion(
    suggestion_id: int,
    body: UpdateStatus,
    db: AsyncSession = Depends(get_db),
):
    """Update cart suggestion status."""
    suggestion = await db.get(CartSuggestion, suggestion_id)
    if not suggestion:
        raise HTTPException(404, "Suggestion not found")
    suggestion.status = body.status
    await db.commit()
    return {"id": suggestion.id, "status": suggestion.status}
