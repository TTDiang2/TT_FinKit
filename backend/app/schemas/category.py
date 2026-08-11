from pydantic import BaseModel


class CategoryCreate(BaseModel):
    type: str
    name: str
    color: str = "#6B6B6B"
    icon: str = ""
    sort_order: int = 0
    is_necessary: bool = False
    pl_section: str = ""
    cf_section: str = ""


class CategoryUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
    icon: str | None = None
    sort_order: int | None = None
    is_necessary: bool | None = None
    pl_section: str | None = None
    cf_section: str | None = None


class CategoryResponse(BaseModel):
    id: str
    user_id: str
    type: str
    name: str
    color: str
    icon: str
    sort_order: int
    is_necessary: bool = False
    pl_section: str = ""
    cf_section: str = ""
    created_at: str
    updated_at: str