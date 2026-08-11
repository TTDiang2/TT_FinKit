from pydantic import BaseModel


class TagCreate(BaseModel):
    name: str
    color: str = "#6B6B6B"


class TagUpdate(BaseModel):
    name: str | None = None
    color: str | None = None


class TagResponse(BaseModel):
    id: str
    user_id: str
    name: str
    color: str
    created_at: str