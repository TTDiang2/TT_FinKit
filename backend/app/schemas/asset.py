from pydantic import BaseModel


class AssetCreate(BaseModel):
    name: str
    asset_type: str  # fixed_asset, cash_equivalent, investment, other_asset, liability
    value: float = 0.0
    description: str | None = None
    acquisition_date: str | None = None
    notes: str | None = None


class AssetUpdate(BaseModel):
    name: str | None = None
    asset_type: str | None = None
    value: float | None = None
    description: str | None = None
    acquisition_date: str | None = None
    notes: str | None = None


class AssetResponse(BaseModel):
    id: str
    user_id: str
    name: str
    asset_type: str
    value: float
    description: str | None
    acquisition_date: str | None
    notes: str | None
    created_at: str
    updated_at: str