"""AI 财富咨询 — 严厉财富审计师人设（用户要求：理性、绝对冷静、锐利、不和稀泠）。

数据契约：AI 只能引用 finance_snapshot 里提供的真实数字；数据不足时必须明说。
人设文档（个人画像）存 user_settings.monitor_thresholds JSON 的 advisor_profile 键，
UI 可编辑；首次使用时落默认模板（含用户口述的目标与约束）。
会话历史存 advisor_chats 表。
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from uuid import uuid4

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.ai_preset import AiPreset
from ..models.user_settings import UserSettings
from .finance_snapshot import finance_snapshot

DEFAULT_PROFILE = """# 个人画像

## 身份与时间线（审计基准，务必先读这一节）
- **2026-07-03 毕业**，此前身份是在校学生。
- **2026-08-25 收到人生第一笔工资**——职业生涯的实际起点（至今约 1 个月）。
- **关键口径警告**：快照中 2026-08 之前的收入全部来自**家庭支持 + 奖学金 + 零星兼职**，
  属于学生阶段收入，不代表当前收入结构。
  - ❌ 错误做法：用"过去 12 个月收入中家庭支持占 54%"论证"收入不自主"——那是历史数据。
  - ✅ 正确做法：评价当前收入自主度，只看 2026-08（含）之后的记录；
    若样本不足 3 个月，应直接写"工资记录样本不足 N 个月，暂不足以评估收入稳定性"，
    而不是拿学生阶段的家庭支持去凑数。

## 当前收入结构（2026-08 起）
- 税后到手：约 **27,000 元/月**（税前约 40,000 元/月）
- 住房公积金：合计 **12,960 元/月**（个人缴 6,480 + 公司缴 6,480）
  - 个人部分占税前约 16%，高于法定基本比例，属含补充公积金的高缴存方案
  - **性质**：强制储蓄，日常不可动用；可用于购房首付提取或按月冲抵月供
  - **量级**：年累积 155,520 元，是购房测算中最重要的变量，不得忽略
- 首月（2026-08）因含一次性项目不代表常态水平，需连续观察 3~6 个月才能定论

## 投资纪律
- 投资以基金为主（指数增强、行业/主题、黄金、债券、货基），接受中高波动
- 已具备主动调仓行为（近 12 个月有 22 笔买入、17 笔卖出），非"只买不卖"
- 投资资金与应急资金**必须分账**：投资账户余额不得充当应急储备

## 目标与约束
- 应急储备：至少覆盖 **6 个月**支出（硬约束，只算现金类账户，不含投资账户与持仓）
- 购房目标：目标城市 **南京 / 上海 双场景对比**，90㎡ 刚需，**5 年内**
  - 参考单价：南京约 3.2 万/㎡、上海约 6.5 万/㎡（详见快照 housing_profile 的场景测算）
  - 首付家庭支持上限：**200 万元**（不依赖则按纯自筹能力评估）
  - 硬约束：不得为凑首付掏空应急储备；月供需在自己供得起的范围内核算，
    且**测算月供承受力时必须计入公积金冲抵**（12,960 元/月）

## 性格与偏好
- 能接受严厉、直接的批评；讨厌和稀泥式的安慰
- 希望得到可执行的数字级建议（金额/比例/期限），不是空话
- 反感基于错误前提的批评——下判断前先核对快照口径与时间线
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
   （消费结构 / 收入与储蓄率 / 应急储备 / 投资组合 / 与购房目标的差距——有数据才写）
   ## 本月行动清单
   （3~6 条可勾选的具体动作，含数字）
   ## 数据缺口
   （本快照看不到但影响判断的信息，没有则写"无"）

## 数据口径（引用前必读——违反即为错误审计）
1. **应急覆盖月数**只统计现金类账户（消费/工资），已排除投资账户余额与持仓市值。
   不得把投资资金再加回去凑"实际可动用储备"——那正是用户明确要避免的双重记账。
2. **收入**已排除系统自动写入的「投资月度盈亏」浮动盈亏流水（金额见 income_profile.excluded），
   该盈亏已体现在持仓市值中，重复计入会虚增收入。
3. **投资买卖**记录在 investment_transactions 表，investment_profile 的
   12m_buy_count / 12m_sell_count 等字段即来自该表；记账流水的 transactions 表
   只有 income/expense/transfer 三种类型，查不到买卖属于口径错误而非"没调过仓"。
4. **投资账户对账恒等式**：投资账户余额 = 累计入金 − 累计出金 + 累计已入账盈亏。
   快照的 investment_reconciliation 已直接给出差额；**差额为 0 即完全勾稽**，
   此时不得再宣称"数据无法勾稽/自相矛盾"。
5. **时间线**：用户 2026-07-03 毕业、2026-08-25 首次领薪。评价收入自主度时
   不得把毕业前的家庭支持/奖学金计入当期收入结构（详见个人画像第一节）。
6. **购房测算**必须计入公积金：用户每月公积金合计 12,960 元，可直接冲抵月供。
   只按到手现金推算月供承受力会系统性低估购房能力。
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
    session_id = uuid4().hex
    timeout = httpx.Timeout(connect=15.0, read=420.0, write=30.0, pool=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(url, json=payload, headers=headers)
        if r.status_code >= 400:
            raise RuntimeError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
        answer = r.json()["choices"][0]["message"]["content"]

    await _save_chat(db, question, answer, snap, user_id, session_id)
    return {"status": "ok", "answer": answer, "snapshot": snap, "session_id": session_id}


async def _save_chat(db: AsyncSession, question: str, answer: str, snap: dict,
                     user_id: str | None = None, session_id: str | None = None) -> None:
    from sqlalchemy import text as _text
    sid = session_id or uuid4().hex
    await db.execute(_text(
        "INSERT INTO advisor_chats (role, content, question, snapshot_json, user_id, session_id) "
        "VALUES ('user', :q, :q, :snap, :u, :sid)"),
        {"q": question, "snap": json.dumps(snap, ensure_ascii=False), "u": user_id, "sid": sid},
    )
    await db.execute(_text(
        "INSERT INTO advisor_chats (role, content, question, snapshot_json, user_id, session_id) "
        "VALUES ('assistant', :a, :q, NULL, :u, :sid)"),
        {"a": answer, "q": question, "u": user_id, "sid": sid},
    )
    await db.commit()


async def stream_ask_advisor(db: AsyncSession, user_id: str, question: str):
    """SSE generator: yields `data: {"delta": ...}` chunks, then `{"done": true}`."""
    preset, url, payload, headers, snap = await _build_ask_payload(db, user_id, question, stream=True)
    if preset is None:
        yield _sse({"error": "未配置 AI preset（设置 → AI 预设）"})
        return
    session_id = uuid4().hex
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
        await _save_chat(db, question, answer, snap, user_id, session_id)
        yield _sse({"done": True})
    except Exception as e:
        yield _sse({"error": f"{type(e).__name__}: {e}"[:300]})


DEFAULT_SESSION_ID = "legacy"

ACTIONS_CATEGORY_HINTS = ("emergency", "invest", "housing", "spending", "income", "other")


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
    # ---- advisor_chats: 多账号隔离 + 会话分组（2026-09-04）----
    cols = {r[1] for r in conn.execute("PRAGMA table_info(advisor_chats)")}
    if "user_id" not in cols:
        conn.execute("ALTER TABLE advisor_chats ADD COLUMN user_id TEXT")
        conn.execute(
            "UPDATE advisor_chats SET user_id = "
            "(SELECT id FROM users ORDER BY created_at LIMIT 1) WHERE user_id IS NULL"
        )
    if "session_id" not in cols:
        conn.execute("ALTER TABLE advisor_chats ADD COLUMN session_id TEXT")
        # 历史数据按 (user_id, question) 归并：同一问题下的 user/assistant 视为同一会话
        for uid, q in conn.execute(
            "SELECT DISTINCT COALESCE(user_id,''), COALESCE(question,'') "
            "FROM advisor_chats WHERE session_id IS NULL"
        ).fetchall():
            sid = uuid4().hex
            conn.execute(
                "UPDATE advisor_chats SET session_id=? WHERE session_id IS NULL "
                "AND COALESCE(user_id,'')=? AND COALESCE(question,'')=?",
                (sid, uid, q),
            )

    # ---- advisor_actions: AI 建议落地为可勾选的行动清单 ----
    conn.execute("""
        CREATE TABLE IF NOT EXISTS advisor_actions (
            id VARCHAR PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            detail TEXT,
            category TEXT DEFAULT 'other',
            target_amount REAL,
            due_date TEXT,
            status TEXT DEFAULT 'todo',
            source TEXT DEFAULT 'manual',
            source_session_id TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT
        )
    """)
    conn.commit()
    conn.close()

