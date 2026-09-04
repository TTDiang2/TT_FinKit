"""AI 财富咨询 — 严厉财富审计师人设（用户要求：理性、绝对冷静、锐利、不和稀泠）。

数据契约：AI 只能引用 finance_snapshot 里提供的真实数字；数据不足时必须明说。
人设文档（个人画像）存 user_settings.monitor_thresholds JSON 的 advisor_profile 键，
UI 可编辑；首次使用时落默认模板（含用户口述的目标与约束）。
会话历史存 advisor_chats 表。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.ai_preset import AiPreset
from ..models.user_settings import UserSettings
from .finance_snapshot import finance_snapshot

DEFAULT_PROFILE = """# 个人画像

## 收入
- 工资为主，月入约 1.0万~1.7万（有奖金/补贴波动），另有少量奖学金/补贴类收入
- 家庭支持的可能性存在（尤其购房时），但不应作为日常现金流依赖

## 投资纪律
- 每月固定投入约 1 万元到投资账户（定投为主）
- 投资品种：基金定投（指数增强、行业/主题基金、黄金、债券），接受中高波动

## 目标与约束
- 应急储备：至少覆盖 6 个月支出（硬约束）
- 中期目标：未来 5~10 年内购房；可能获得父母家庭支持，但要求自己独立供得起月供
- 购房前提：月供不超过家庭月收入的合理比例，且不掏空应急储备

## 性格与偏好
- 能接受严厉、直接的批评；讨厌和稀泠式的安慰
- 希望得到可执行的数字级建议（金额/比例/期限），不是空话
"""

SYSTEM_PROMPT = """你是一名极其严格、绝对冷静的个人财富管理审计师，服务对象是一位年轻职场人士。

你不是他的朋友，不是销售，绝不做情绪安抚。你的职责是像审计师一样，
基于他提供的真实数据，指出每一处财务纪律上的漏洞。

## 铁律
1. 只引用【财务数据快照】里的具体数字说话（月份、金额、百分比），禁止无数据支撑的泛泛而谈。
2. 直接指出问题：消费浪费、储蓄率不足、应急金缺口、投资纪律漂移、风险暴露失衡——按严重程度排序，有多少说多少。
3. 每一条批评必须配一个可执行动作（具体金额/比例/期限），禁止"建议保持""注意控制"这类空话。
4. 表现好的地方最多一句客观确认，不夸张、不表扬性铺垫。
5. 语气冷静、克制、锐利；可以尖锐，但不侮辱、不讽刺人格。用专业术语（储蓄率、应急覆盖月数、现金流结构、资产配置暴露、最大回撤）。
6. 数据不足以判断某项时，明确写"数据不足以判断 X"并指出缺什么数据，禁止编造。
7. 输出结构：
   ## 核心结论
   （3~5 条，按严重程度排序，每条一句话+关键数字）
   ## 逐项分析
   （消费结构 / 收入与储蓄率 / 应急储备 / 投资组合 / 与目标的差距——有数据才写）
   ## 本月行动清单
   （3~6 条可勾选的具体动作，含数字）
   ## 数据缺口
   （本快照看不到但影响判断的信息，没有则写"无"）
"""


async def _pick_preset(db: AsyncSession, user_id: str) -> AiPreset | None:
    preset = (await db.execute(
        select(AiPreset).where(AiPreset.user_id == user_id, AiPreset.is_default == "true").limit(1)
    )).scalars().first()
    if not preset:
        preset = (await db.execute(
            select(AiPreset).where(AiPreset.user_id == user_id).limit(1)
        )).scalars().first()
    return preset


async def get_profile(db: AsyncSession, user_id: str) -> str:
    row = (await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
           ).scalar_one_or_none()
    if not row or not row.monitor_thresholds:
        return DEFAULT_PROFILE
    try:
        data = json.loads(row.monitor_thresholds)
        return data.get("advisor_profile") or DEFAULT_PROFILE
    except (ValueError, TypeError):
        return DEFAULT_PROFILE


async def save_profile(db: AsyncSession, user_id: str, profile_md: str) -> None:
    row = (await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
           ).scalar_one_or_none()
    if row is None:
        row = UserSettings(user_id=user_id)
        db.add(row)
    current: dict = {}
    if row.monitor_thresholds:
        try:
            current = json.loads(row.monitor_thresholds)
        except (ValueError, TypeError):
            current = {}
    current["advisor_profile"] = profile_md
    row.monitor_thresholds = json.dumps(current, ensure_ascii=False)
    await db.commit()


def _sse(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


async def _build_ask_payload(db: AsyncSession, user_id: str, question: str,
                             stream: bool):
    preset = await _pick_preset(db, user_id)
    if preset is None:
        return None, None, None, None, None
    snap = await finance_snapshot(db, user_id)
    profile = await get_profile(db, user_id)
    snapshot_md = "```json\n" + json.dumps(snap, ensure_ascii=False, indent=1) + "\n```"
    user_prompt = (
        f"# 个人画像（用户自述，可被数据修正）\n{profile}\n\n"
        f"# 财务数据快照（真实记账数据，{snap['as_of']})\n{snapshot_md}\n\n"
        f"# 用户提问\n{question}\n\n"
        "按系统铁律输出。"
    )
    url = preset.api_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url = (url + "/chat/completions") if url.endswith("/v1") else (url.rstrip("/") + "/v1/chat/completions")
    payload = {
        "model": preset.model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.4,
        "stream": stream,
    }
    headers = {"Authorization": f"Bearer {preset.api_key}", "Content-Type": "application/json"}
    return preset, url, payload, headers, snap


async def ask_advisor(db: AsyncSession, user_id: str, question: str) -> dict:
    preset, url, payload, headers, snap = await _build_ask_payload(db, user_id, question, stream=False)
    if preset is None:
        return {"status": "error", "error": "未配置 AI preset（设置 → AI 预设）"}
    timeout = httpx.Timeout(connect=15.0, read=420.0, write=30.0, pool=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload, headers=headers)
        if r.status_code >= 400:
            raise RuntimeError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
        answer = r.json()["choices"][0]["message"]["content"]

    await _save_chat(db, question, answer, snap)
    return {"status": "ok", "answer": answer, "snapshot": snap}


async def _save_chat(db: AsyncSession, question: str, answer: str, snap: dict) -> None:
    from sqlalchemy import text as _text
    await db.execute(_text(
        "INSERT INTO advisor_chats (role, content, question, snapshot_json) "
        "VALUES ('user', :q, :q, :snap)"),
        {"q": question, "snap": json.dumps(snap, ensure_ascii=False)},
    )
    await db.execute(_text(
        "INSERT INTO advisor_chats (role, content, question, snapshot_json) "
        "VALUES ('assistant', :a, :q, NULL)"),
        {"a": answer, "q": question},
    )
    await db.commit()


async def stream_ask_advisor(db: AsyncSession, user_id: str, question: str):
    """SSE generator: yields `data: {"delta": ...}` chunks, then `{"done": true}`."""
    preset, url, payload, headers, snap = await _build_ask_payload(db, user_id, question, stream=True)
    if preset is None:
        yield _sse({"error": "未配置 AI preset（设置 → AI 预设）"})
        return
    acc: list[str] = []
    timeout = httpx.Timeout(connect=15.0, read=420.0, write=30.0, pool=15.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as r:
                if r.status_code >= 400:
                    body = (await r.aread()).decode("utf-8", "replace")
                    yield _sse({"error": f"LLM HTTP {r.status_code}: {body[:200]}"})
                    return
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta_obj = (obj.get("choices") or [{}])[0].get("delta") or {}
                    if delta_obj.get("reasoning_content"):
                        yield _sse({"reasoning": delta_obj["reasoning_content"]})
                    delta = delta_obj.get("content")
                    if delta:
                        acc.append(delta)
                        yield _sse({"delta": delta})
        answer = "".join(acc)
        await _save_chat(db, question, answer, snap)
        yield _sse({"done": True})
    except Exception as e:
        yield _sse({"error": f"{type(e).__name__}: {e}"[:300]})


def ensure_tables(db_path: str) -> None:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS advisor_chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            question TEXT,
            snapshot_json TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

