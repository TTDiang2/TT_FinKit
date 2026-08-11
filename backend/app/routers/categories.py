from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models.category import Category
from ..schemas.category import CategoryCreate, CategoryUpdate, CategoryResponse
from ..middleware.auth import get_current_user_id
from typing import List

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=List[CategoryResponse])
async def get_categories(user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).where(Category.user_id == user_id).order_by(Category.type, Category.sort_order))
    cats = result.scalars().all()
    return [CategoryResponse(
        id=c.id, user_id=c.user_id, type=c.type, name=c.name, color=c.color,
        icon=c.icon, sort_order=c.sort_order, is_necessary=c.is_necessary or False,
        pl_section=c.pl_section or "", cf_section=c.cf_section or "",
        created_at=str(c.created_at), updated_at=str(c.updated_at)
    ) for c in cats]


@router.post("", response_model=CategoryResponse)
async def create_category(req: CategoryCreate, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    cat = Category(user_id=user_id, **req.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return CategoryResponse(
        id=cat.id, user_id=cat.user_id, type=cat.type, name=cat.name, color=cat.color,
        icon=cat.icon, sort_order=cat.sort_order, is_necessary=cat.is_necessary or False,
        pl_section=cat.pl_section or "", cf_section=cat.cf_section or "",
        created_at=str(cat.created_at), updated_at=str(cat.updated_at)
    )


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(category_id: str, req: CategoryUpdate, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).where(Category.id == category_id, Category.user_id == user_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(cat, key, value)
    await db.commit()
    await db.refresh(cat)
    return CategoryResponse(
        id=cat.id, user_id=cat.user_id, type=cat.type, name=cat.name, color=cat.color,
        icon=cat.icon, sort_order=cat.sort_order, is_necessary=cat.is_necessary or False,
        pl_section=cat.pl_section or "", cf_section=cat.cf_section or "",
        created_at=str(cat.created_at), updated_at=str(cat.updated_at)
    )


@router.delete("/{category_id}")
async def delete_category(category_id: str, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Category).where(Category.id == category_id, Category.user_id == user_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    await db.delete(cat)
    await db.commit()
    return {"message": "Category deleted"}