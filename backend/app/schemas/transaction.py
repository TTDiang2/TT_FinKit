from pydantic import BaseModel
from typing import List, Optional


class TransactionCreate(BaseModel):
    type: str
    date: str
    amount: float
    account_id: str
    dest_account_id: str | None = None
    category_id: str | None = None
    tag_ids: List[str] = []
    description: str = ""
    remark: str = ""
    location: str = ""


class TransactionUpdate(BaseModel):
    type: str | None = None
    date: str | None = None
    amount: float | None = None
    account_id: str | None = None
    dest_account_id: str | None = None
    category_id: str | None = None
    tag_ids: List[str] | None = None
    description: str | None = None
    remark: str | None = None
    location: str | None = None


class TransactionResponse(BaseModel):
    id: str
    user_id: str
    type: str
    date: str
    amount: float
    account_id: str
    dest_account_id: str | None
    category_id: str | None
    tag_ids: List[str]
    description: str
    remark: str
    location: str = ""
    created_at: str
    updated_at: str
    account_name: str = ""
    category_name: str = ""
    category_color: str = ""


# ---- 批量导入 ----

class DuplicateCandidate(BaseModel):
    """与待导入行可能重复的现有交易（用于前端展示"与什么重复"）。"""
    date: str
    amount: float
    type: str                          # income / expense / transfer
    account: str = ""                  # 本方账户名
    description: str = ""
    location: str = ""


class ImportPreviewRow(BaseModel):
    row_index: int                      # Excel 中的行号（从 2 开始，1=表头）
    date: str
    direction: str                      # income / expense / transfer
    amount: float
    account: str                        # 本方账户名
    dest_account: str = ""              # 对方账户名（仅 transfer）
    category: str = ""                  # 分类名
    tags: str = ""                      # 分号分隔
    description: str = ""
    remark: str = ""
    source_memo: str = ""
    counterparty: str = ""
    location: str = ""                  # 交易地点/附言
    confidence: str = ""                # 置信度 high/medium/low/none（ccb 脚本打标）
    # 解析结果
    error: str = ""                     # 非空=该行无法导入（格式错误/账户分类不存在）
    is_duplicate: bool = False          # 与现有交易重复
    duplicate_with: List[DuplicateCandidate] = []  # 重复候选（is_duplicate=True 时有值）


class ImportPreviewResponse(BaseModel):
    rows: List[ImportPreviewRow]
    total: int
    error_count: int
    duplicate_count: int
    # 供前端下拉/校验用
    accounts: List[str]
    expense_categories: List[str]
    income_categories: List[str]


class ImportCommitRow(BaseModel):
    date: str
    direction: str
    amount: float
    account: str
    dest_account: str = ""
    category: str = ""
    tags: str = ""
    description: str = ""
    remark: str = ""
    location: str = ""


class ImportCommitRequest(BaseModel):
    rows: List[ImportCommitRow]


class ImportResult(BaseModel):
    inserted: int
    skipped: int
    errors: List[str]