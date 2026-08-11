from pydantic import BaseModel


class AccountCreate(BaseModel):
    name: str
    currency: str = "CNY"
    initial_balance: float = 0.0
    account_type: str = "cash"
    hidden: bool = False
    sort_order: int = 0


class AccountUpdate(BaseModel):
    name: str | None = None
    currency: str | None = None
    initial_balance: float | None = None
    account_type: str | None = None
    hidden: bool | None = None
    sort_order: int | None = None


class AccountResponse(BaseModel):
    id: str
    user_id: str
    name: str
    currency: str
    initial_balance: float
    account_type: str = "cash"
    hidden: bool
    sort_order: int
    current_balance: float = 0.0
    created_at: str
    updated_at: str