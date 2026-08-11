from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_db
from ..models.ai_preset import AiPreset
from ..schemas.ai_preset import AiPresetCreate, AiPresetUpdate, AiPresetResponse
from ..middleware.auth import get_current_user_id
from typing import List

router = APIRouter(prefix="/api/ai-presets", tags=["ai-presets"])


@router.get("", response_model=List[AiPresetResponse])
async def get_presets(user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AiPreset).where(AiPreset.user_id == user_id).order_by(AiPreset.created_at))
    presets = result.scalars().all()
    return [AiPresetResponse(
        id=p.id, user_id=p.user_id, name=p.name, api_url=p.api_url or "",
        api_key=p.api_key or "", model_name=p.model_name or "",
        system_prompt=p.system_prompt or "", is_default=p.is_default == "true",
        created_at=str(p.created_at), updated_at=str(p.updated_at)
    ) for p in presets]


@router.post("", response_model=AiPresetResponse)
async def create_preset(req: AiPresetCreate, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    preset = AiPreset(user_id=user_id, name=req.name, api_url=req.api_url,
                      api_key=req.api_key, model_name=req.model_name,
                      system_prompt=req.system_prompt, is_default="true" if req.is_default else "false")
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return AiPresetResponse(
        id=preset.id, user_id=preset.user_id, name=preset.name, api_url=preset.api_url or "",
        api_key=preset.api_key or "", model_name=preset.model_name or "",
        system_prompt=preset.system_prompt or "", is_default=preset.is_default == "true",
        created_at=str(preset.created_at), updated_at=str(preset.updated_at)
    )


@router.put("/{preset_id}", response_model=AiPresetResponse)
async def update_preset(preset_id: str, req: AiPresetUpdate, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AiPreset).where(AiPreset.id == preset_id, AiPreset.user_id == user_id))
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    for key, value in req.model_dump(exclude_unset=True).items():
        if key == "is_default":
            setattr(preset, key, "true" if value else "false")
        else:
            setattr(preset, key, value)
    await db.commit()
    await db.refresh(preset)
    return AiPresetResponse(
        id=preset.id, user_id=preset.user_id, name=preset.name, api_url=preset.api_url or "",
        api_key=preset.api_key or "", model_name=preset.model_name or "",
        system_prompt=preset.system_prompt or "", is_default=preset.is_default == "true",
        created_at=str(preset.created_at), updated_at=str(preset.updated_at)
    )


@router.delete("/{preset_id}")
async def delete_preset(preset_id: str, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AiPreset).where(AiPreset.id == preset_id, AiPreset.user_id == user_id))
    preset = result.scalar_one_or_none()
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    await db.delete(preset)
    await db.commit()
    return {"message": "Preset deleted"}
