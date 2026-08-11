from pydantic import BaseModel, ConfigDict


class AiPresetCreate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: str
    api_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model_name: str = "gpt-4o"
    system_prompt: str = ""
    is_default: bool = False


class AiPresetUpdate(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: str | None = None
    api_url: str | None = None
    api_key: str | None = None
    model_name: str | None = None
    system_prompt: str | None = None
    is_default: bool | None = None


class AiPresetResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    user_id: str
    name: str
    api_url: str
    api_key: str
    model_name: str
    system_prompt: str
    is_default: bool = False
    created_at: str
    updated_at: str
