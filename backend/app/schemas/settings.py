from pydantic import BaseModel
from typing import Optional


class SettingsUpdate(BaseModel):
    language: Optional[str] = None
    currency_symbol: Optional[str] = None
    date_format: Optional[str] = None
    timezone: Optional[str] = None
    sidebar_expanded: Optional[bool] = None
    # AI investment analysis
    ai_search_backend: Optional[str] = None      # "duckduckgo" | "tavily"
    ai_search_api_key: Optional[str] = None
    ai_investment_preset_id: Optional[str] = None
    # iFinD credentials (同花顺 quantapi)
    ifind_username: Optional[str] = None
    ifind_password: Optional[str] = None


class SettingsResponse(BaseModel):
    language: str
    currency_symbol: str
    date_format: str
    timezone: str
    sidebar_expanded: bool
    # AI investment analysis
    ai_search_backend: str = "duckduckgo"
    ai_search_api_key: str = ""
    ai_investment_preset_id: Optional[str] = None
    # iFinD credentials (同花顺 quantapi)
    ifind_username: str = ""
    # NOTE: password is intentionally NOT echoed back in the response to avoid
    # leaking it via the GET endpoint. The frontend keeps its own masked copy.
    has_ifind_password: bool = False
