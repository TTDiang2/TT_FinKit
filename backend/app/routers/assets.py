from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models.asset import Asset
from ..schemas.asset import AssetCreate, AssetUpdate, AssetResponse
from ..middleware.auth import get_current_user_id
from typing import List

router = APIRouter(prefix="/api/assets", tags=["assets"])


@router.get("", response_model=List[AssetResponse])
async def get_assets(user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Asset).where(Asset.user_id == user_id))
    assets = result.scalars().all()
    return [AssetResponse(
        id=a.id, user_id=a.user_id, name=a.name, asset_type=a.asset_type,
        value=a.value, description=a.description, acquisition_date=a.acquisition_date,
        notes=a.notes, created_at=str(a.created_at), updated_at=str(a.updated_at)
    ) for a in assets]


@router.post("", response_model=AssetResponse)
async def create_asset(req: AssetCreate, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    asset = Asset(user_id=user_id, **req.model_dump())
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return AssetResponse(
        id=asset.id, user_id=asset.user_id, name=asset.name, asset_type=asset.asset_type,
        value=asset.value, description=asset.description, acquisition_date=asset.acquisition_date,
        notes=asset.notes, created_at=str(asset.created_at), updated_at=str(asset.updated_at)
    )


@router.get("/{asset_id}", response_model=AssetResponse)
async def get_asset(asset_id: str, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return AssetResponse(
        id=asset.id, user_id=asset.user_id, name=asset.name, asset_type=asset.asset_type,
        value=asset.value, description=asset.description, acquisition_date=asset.acquisition_date,
        notes=asset.notes, created_at=str(asset.created_at), updated_at=str(asset.updated_at)
    )


@router.put("/{asset_id}", response_model=AssetResponse)
async def update_asset(asset_id: str, req: AssetUpdate, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    for key, value in req.model_dump(exclude_unset=True).items():
        setattr(asset, key, value)
    await db.commit()
    await db.refresh(asset)
    return AssetResponse(
        id=asset.id, user_id=asset.user_id, name=asset.name, asset_type=asset.asset_type,
        value=asset.value, description=asset.description, acquisition_date=asset.acquisition_date,
        notes=asset.notes, created_at=str(asset.created_at), updated_at=str(asset.updated_at)
    )


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Asset).where(Asset.id == asset_id, Asset.user_id == user_id))
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    await db.delete(asset)
    await db.commit()
    return {"message": "Asset deleted"}