from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..database import get_private_db
from ..models.user import User
from ..models.user_settings import UserSettings
from ..schemas.auth import RegisterRequest, LoginRequest, TokenResponse, UserResponse, ForgotPasswordRequest
from ..utils.security import hash_password, verify_password, create_access_token
from ..middleware.auth import get_current_user_id

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_private_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=req.email, password_hash=hash_password(req.password), name=req.name)
    db.add(user)
    await db.flush()

    settings_model = UserSettings(user_id=user.id)
    db.add(settings_model)
    await db.commit()

    # 发行包场景：首个用户注册后立刻认领 public 库数据（标的/组合/因子），
    # 否则要等下次重启才可见。开发环境作者即主用户 → no-op。
    try:
        from fastapi.concurrency import run_in_threadpool
        from ..services.db_adopt import adopt_public_assets
        await run_in_threadpool(adopt_public_assets)
    except Exception:  # noqa: BLE001 — 认领失败不阻塞注册
        pass

    token = create_access_token({"sub": user.id})
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_private_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": user.id})
    return TokenResponse(access_token=token)


@router.post("/logout")
async def logout():
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_me(user_id: str = Depends(get_current_user_id), db: AsyncSession = Depends(get_private_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(id=user.id, email=user.email, name=user.name, created_at=str(user.created_at))


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, db: AsyncSession = Depends(get_private_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user:
        return {"message": "If email exists, reset link has been sent"}
    return {"message": "If email exists, reset link has been sent"}