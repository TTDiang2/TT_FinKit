from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from ..database import get_db
from ..models.user_settings import UserSettings
from ..models.user import User
from ..schemas.settings import SettingsUpdate, SettingsResponse
from ..middleware.auth import get_current_user_id
from ..utils.security import hash_password, verify_password
from ..utils.crypto import encrypt_field

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsResponse)
async def get_settings(user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserSettings(user_id=user_id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return SettingsResponse(
        language=settings.language, currency_symbol=settings.currency_symbol,
        date_format=settings.date_format, timezone=settings.timezone, sidebar_expanded=settings.sidebar_expanded,
        ai_search_backend=settings.ai_search_backend or "duckduckgo",
        ai_search_api_key=settings.ai_search_api_key or "",
        ai_investment_preset_id=settings.ai_investment_preset_id,
        ifind_username=settings.ifind_username or "",
        has_ifind_password=bool(settings.ifind_password),
    )


@router.put("", response_model=SettingsResponse)
async def update_settings(req: SettingsUpdate, user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = UserSettings(user_id=user_id)
        db.add(settings)

    data = req.model_dump(exclude_unset=True)
    # Never blank out an existing password when the client sends an empty string
    # (the masked UI flow): only update if a non-empty value is provided.
    if data.get("ifind_password") == "":
        data.pop("ifind_password", None)
    elif "ifind_password" in data:
        # Encrypt at rest — never store the iFinD password in plaintext
        data["ifind_password"] = encrypt_field(data["ifind_password"])
    for key, value in data.items():
        setattr(settings, key, value)
    await db.commit()
    await db.refresh(settings)
    return SettingsResponse(
        language=settings.language, currency_symbol=settings.currency_symbol,
        date_format=settings.date_format, timezone=settings.timezone, sidebar_expanded=settings.sidebar_expanded,
        ai_search_backend=settings.ai_search_backend or "duckduckgo",
        ai_search_api_key=settings.ai_search_api_key or "",
        ai_investment_preset_id=settings.ai_investment_preset_id,
        ifind_username=settings.ifind_username or "",
        has_ifind_password=bool(settings.ifind_password),
    )


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class IFindTestRequest(BaseModel):
    username: str
    password: str


@router.post("/ifind/test")
async def test_ifind(req: IFindTestRequest):
    """Connectivity check for iFinD credentials (used by the settings page)."""
    from ..services import ifind_client
    if not ifind_client.is_available():
        return {"ok": False, "error": f"iFinDPy 不可用: {ifind_client.import_error() or '未安装'}"}
    try:
        await ifind_client.ensure_logged_in(req.username, req.password)
        return {"ok": True, "message": "iFinD 登录成功"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.put("/password")
async def change_password(
    req: PasswordChangeRequest,
    user_id: str = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not verify_password(req.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = hash_password(req.new_password)
    await db.commit()
    return {"message": "Password changed successfully"}


@router.delete("/account")
async def delete_account(user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await db.delete(user)
    await db.commit()
    return {"message": "Account deleted successfully"}