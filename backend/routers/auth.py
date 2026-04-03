from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_db
from backend.models import User
from backend.silpo.auth import request_otp, verify_otp

router = APIRouter(prefix="/auth", tags=["auth"])


class OTPRequest(BaseModel):
    phone: str
    delivery_method: str = "sms"


class OTPVerify(BaseModel):
    phone: str
    code: str


@router.post("/request-otp")
async def send_otp(body: OTPRequest):
    try:
        result = await request_otp(body.phone, body.delivery_method)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))


@router.post("/verify-otp")
async def check_otp(body: OTPVerify, db: AsyncSession = Depends(get_db)):
    try:
        result = await verify_otp(body.phone, body.code)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(502, str(e))

    # Create or get user
    user = (await db.execute(select(User).where(User.phone == body.phone))).scalar_one_or_none()
    if not user:
        user = User(phone=body.phone)
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return {
        "access_token": result["access_token"],
        "phone": result["phone"],
        "user": {"id": user.id, "phone": user.phone, "name": user.name},
    }
