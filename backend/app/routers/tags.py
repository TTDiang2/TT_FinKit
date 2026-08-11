from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models.tag import Tag
from ..schemas.tag import TagCreate, TagUpdate, TagResponse
from ..middleware.auth import get_current_user_id
from typing import List

router = APIRouter(prefix="/api/tags", tags=["tags"])


@router.get("", response_model=List[TagResponse])
async def get_tags(user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tag).where(Tag.user_id == user_id))
    tags = result.scalars().all()
    return [TagResponse(id=t.id, user_id=t.user_id, name=t.name, color=t.color, created_at=str(t.created_at)) for t in tags]


@router.post("", response_model=TagResponse)
async def create_tag(req: TagCreate, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    tag = Tag(user_id=user_id, **req.model_dump())
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return TagResponse(id=tag.id, user_id=tag.user_id, name=tag.name, color=tag.color, created_at=str(tag.created_at))


@router.put("/{tag_id}", response_model=TagResponse)
async def update_tag(tag_id: str, req: TagUpdate, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(tag, key, value)
    await db.commit()
    await db.refresh(tag)
    return TagResponse(id=tag.id, user_id=tag.user_id, name=tag.name, color=tag.color, created_at=str(tag.created_at))


@router.delete("/{tag_id}")
async def delete_tag(tag_id: str, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tag).where(Tag.id == tag_id, Tag.user_id == user_id))
    tag = result.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.delete(tag)
    await db.commit()
    return {"message": "Tag deleted"}