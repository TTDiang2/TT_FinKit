from pydantic import BaseModel


class ReportArchiveCreate(BaseModel):
    report_type: str
    period_start: str
    period_end: str
    content: str


class ReportArchiveResponse(BaseModel):
    id: str
    user_id: str
    report_type: str
    period_start: str
    period_end: str
    generated_at: str