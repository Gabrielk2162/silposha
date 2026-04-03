from fastapi import APIRouter, Query

from backend.silpo.client import get_categories, search_products

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=50),
    filial_id: str | None = None,
):
    return await search_products(q, filial_id=filial_id, page=page, per_page=per_page)


@router.get("/categories")
async def categories(filial_id: str | None = None):
    return await get_categories(filial_id=filial_id)
