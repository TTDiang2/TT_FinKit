# FinKit — Personal Finance Web App

> 本文档是 FinKit 项目的完整开发规范文档。
> 由 ezBookkeeping 参考 + AutoManga 设计语言驱动，后端重写为 Python FastAPI，前端基于 Vue 3 + Vite。

---

## ⚠️ 文档状态（2026-08 更新）

> **本文档为项目初始设计规范（2026 年初编写），已与当前实现存在显著偏差。**
> 实际实现以代码为准；本文档保留作为设计意图参考。

**与实际实现的差异对照：**

| 章节 | 原设计 | 实际情况 |
|------|--------|----------|
| Tab 导航 | 6 个 tab（管理/首页/记账/审计/统计/报表 + 设置） | **8 个 tab**：首页/记账/**资产**/**投资**/统计/报表/设置/管理；**无"审计"tab**（审计功能未实现，记账页内可编辑） |
| 记账 | 收入/支出/转账三类型 | 已实现（`/bookkeeping`） |
| 资产 | 无此模块 | **新增**：资产模块（`/assets`，后端 `Asset` 模型 + `/api/assets`） |
| 投资 | 无此模块（仅分类默认值含"投资"） | **新增**：完整投资管理模块（`/investments` + `/investments/ai`）→ 详见 `docs/INVESTMENTS.md` |
| 统计 | 多维度图表 | 已实现（`/statistics`） |
| 报表 | BS/PL/CF + 归档 | 已实现（`/reports`），V5 版含 `pl_section`/`cf_section` 分类体系 |
| AI | 无设计 | **新增**：AiPreset 模型 + 投资 AI 分析（搜索→LLM→结构化报告）→ 详见 `docs/plans/2026-04-22-ai-integration-design.md` 及 `docs/INVESTMENTS.md` |
| 加密 | 字段级 AES-256-GCM | iFinD 凭证等敏感字段加密存储（`utils/crypto.py`），其余未全面落地 |
| 后端 | 纯 FastAPI | FastAPI + SQLAlchemy(async) + SQLite + **iFinD（同花顺行情）** + 腾讯财经兜底 |
| 数据模型 | 6 个模型 | **13 个模型**：新增 `Investment`/`InvestmentTransaction`/`InvestmentNavSnapshot`/`InvestmentAiReport`/`AiPreset`/`Asset` 等 |

> 下文各章节若与上述对照冲突，以"实际情况"列为准。

---

## 一、项目概述

### 1.1 项目定位
- **类型**：Personal Finance / Personal Accounting Web Application（个人财务记账网页应用）
- **形态**：自托管网页应用，数据保存在本地，需加密
- **用户模式**：多账户制 —— 注册后创建独立账户，数据按账户隔离，其他账户无法访问

### 1.2 核心目标
1. 安全：本地数据加密存储（AES-256-GCM 或类似），账户之间完全隔离
2. 简约：现代黑白灰 UI，参考 AutoManga 设计语言
3. 完整：从记账 → 审计 → 统计 → 报表全链路覆盖
4. 可存档：报表模块支持历史归档，可查阅过往月报/季报/年报

### 1.3 技术栈

| 层次 | 技术选型 | 说明 |
|------|---------|------|
| **后端** | Python 3.11+ + FastAPI | 异步 API 服务 |
| **数据库** | SQLite（本地）+ SQLAlchemy 2.0 ORM | 单文件，易于备份和迁移 |
| **加密** | cryptography (Fernet/AES-256-GCM) | 本地数据字段级加密 |
| **认证** | JWT (python-jose) + bcrypt | 登录 token + 密码哈希 |
| **前端-框架** | Vue 3.4+ (Composition API) + TypeScript | 严格模式 |
| **前端-构建** | Vite 8 | 开发热更新 + 生产构建 |
| **前端-状态** | Pinia (with persist) | 状态管理 + localStorage 持久化 |
| **前端-路由** | Vue Router 4 | SPA 路由 |
| **前端-UI 库** | Tailwind CSS v3（自定义配置） | 原子化 CSS |
| **图表** | Chart.js 4 + vue-chartjs | 统计图表 |
| **图标** | Feather Icons (lucide-vue-next) | 统一图标风格 |
| **日期** | dayjs | 轻量日期处理 |

> **注**：不考虑 React / Next.js / Nuxt，坚持 Vue 栈。

---

## 二、设计系统

### 2.1 设计哲学
完全遵循 AutoManga 设计语言，黑白灰为主色调，克制而精准的动效，极简主义。

### 2.2 颜色（CSS Variables）

```css
:root {
  /* 背景层级 */
  --bg-primary: #FFFFFF;      /* 主背景 */
  --bg-secondary: #FAFAFA;    /* 次级背景 */
  --bg-tertiary: #F5F5F5;     /* 第三层级 / 卡片悬浮 */
  --bg-sidebar: #F8F8F8;      /* 侧边栏背景 */

  /* 边框 */
  --border-default: #E8E8E8;
  --border-hover: #D4D4D4;

  /* 文字 */
  --text-primary: #1A1A1A;    /* 主文字 */
  --text-secondary: #6B6B6B;  /* 次要文字 */
  --text-muted: #9B9B9B;      /* 辅助/占位文字 */
  --text-inverse: #FFFFFF;   /* 反色文字 */

  /* 强调色 */
  --accent-primary: #000000;  /* 主色调：黑色 */
  --accent-hover: #333333;
  --accent-light: #F5F5F5;   /* 选中态背景 */

  /* 状态色 */
  --success: #4CAF50;
  --success-bg: rgba(76, 175, 80, 0.10);
  --warning: #FF9800;
  --warning-bg: rgba(255, 152, 0, 0.10);
  --error: #F44336;
  --error-bg: rgba(244, 67, 54, 0.10);
  --info: #2196F3;
  --info-bg: rgba(33, 150, 243, 0.10);

  /* 收入/支出专用 */
  --income-color: #4CAF50;
  --expense-color: #F44336;
  --transfer-color: #2196F3;
}
```

### 2.3 字体

```
/* 正文 */
font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;

/* 数字/金额 — 始终等宽，便于对齐 */
font-family: 'JetBrains Mono', 'Fira Code', monospace;

/* 字重 */
--font-normal: 400;
--font-medium: 500;    /* label / 次要 */
--font-semibold: 600;  /* 标题 */
--font-bold: 700;      /* 强调 */

/* 字号 */
--text-xs: 12px;
--text-sm: 13px;
--text-base: 14px;
--text-md: 16px;
--text-lg: 18px;
--text-xl: 20px;
--text-2xl: 24px;
--text-3xl: 32px;
```

### 2.4 圆角

```
--radius-sm: 4px;    /* 按钮/输入框/徽章 */
--radius-md: 8px;     /* 小卡片/下拉 */
--radius-lg: 12px;    /* 模态框/大容器 */
--radius-xl: 16px;    /* 最大圆角 */
```

### 2.5 阴影

```
--shadow-sm: 0 1px 2px rgba(0,0,0,0.04);
--shadow-md: 0 2px 8px rgba(0,0,0,0.06);
--shadow-lg: 0 4px 16px rgba(0,0,0,0.10);
--shadow-xl: 0 8px 32px rgba(0,0,0,0.14);
```

### 2.6 间距（8px 基准网格）

```
--space-1: 4px;   --space-2: 8px;
--space-3: 12px;  --space-4: 16px;
--space-5: 20px;  --space-6: 24px;
--space-8: 32px;  --space-10: 40px;
--space-12: 48px; --space-16: 64px;
```

### 2.7 过渡

```
--transition-fast: 150ms ease-out;
--transition-base: 200ms ease-out;
--transition-slow: 300ms ease-in-out;
```

### 2.8 侧边栏规范

- 宽度：64px（收起态）/ 220px（展开态）
- 图标大小：20px
- 激活态：黑色实心背景 `#000` + 白色图标
- 悬停态：浅灰背景 `#F0F0F0`
- tooltip：左侧弹出，黑色背景，白色文字，12px

### 2.9 滚动条样式

```css
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-secondary); }
::-webkit-scrollbar-thumb {
  background: var(--border-hover);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }
```

### 2.10 动画

```css
/* 页面切换淡入 */
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* 卡片悬浮 */
@keyframes cardHover {
  from { box-shadow: var(--shadow-sm); }
  to   { box-shadow: var(--shadow-md); }
}

/* 加载旋转 */
@keyframes spin { to { transform: rotate(360deg); } }

/* 模态框 */
@keyframes modalIn {
  from { opacity: 0; transform: scale(0.95); }
  to   { opacity: 1; transform: scale(1); }
}
```

---

## 三、功能架构

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────┐
│                    App Shell                         │
│  ┌──────────┐ ┌──────────────────────────────────┐  │
│  │          │ │         Content Area              │  │
│  │ Sidebar  │ │  ┌────────────────────────────┐   │  │
│  │ (tabs)  │ │  │      Page Header            │   │  │
│  │          │ │  ├────────────────────────────┤   │  │
│  │  管理    │ │  │                            │   │  │
│  │  首页    │ │  │       Page Content         │   │  │
│  │  记账    │ │  │                            │   │  │
│  │  审计    │ │  │                            │   │  │
│  │  统计    │ │  └────────────────────────────┘   │  │
│  │  报表    │ │                                    │  │
│  │  设置    │ │                                    │  │
│  │          │ │                                    │  │
│  └──────────┘ └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 3.2 Tab 导航（6 个主 Tab）

| # | Tab 名称 | 图标 (Feather) | 路由 | 权限 |
|---|---------|----------------|------|------|
| 1 | 管理 | `FiSettings` | `/admin` | 登录用户 |
| 2 | 首页 | `FiHome` | `/` | 登录用户 |
| 3 | 记账 | `FiEdit3` | `/bookkeeping` | 登录用户 |
| 4 | 审计 | `FiCheckSquare` | `/audit` | 登录用户 |
| 5 | 统计 | `FiBarChart2` | `/statistics` | 登录用户 |
| 6 | 报表 | `FiFileText` | `/reports` | 登录用户 |
| - | 设置 | `FiSliders` | `/settings` | 登录用户 |

> **认证状态**：
> - 未登录 → 强制跳转 `/login`
> - 已登录 → 可访问以上所有页面
> - 每个用户只能访问自己的数据（后端 JWT 验权 + 数据隔离）

---

## 四、页面详细规范

### 4.1 认证模块

#### 登录页 `/login`
- 页面居中卡片布局，白底，logo + 标题
- 表单：邮箱 + 密码 + 记住我
- 登录按钮：黑色实心 `.btn-primary`
- 下方链接：注册 / 忘记密码
- 登录成功后跳转到首页 `/`

#### 注册页 `/register`
- 表单：邮箱 + 密码 + 确认密码
- 注册成功后自动登录，跳转首页
- 每人可注册多个账户（无邀请码限制）

#### 忘记密码 `/forgot-password`
- 输入邮箱 → 发送重置邮件（邮件功能可简化：显示一次性重置链接，本地发送即可）
- 或简化为：直接设置新密码（无需邮件）

---

### 4.2 管理页 `/admin`（第一个 Tab，侧边栏顶部）

**目的**：账户基础信息管理

#### 账户概览卡片
- 显示：账户名称、邮箱、注册时间、账户余额合计

#### 账户管理
- **账户列表**：展示所有已创建的资金账户
  - 字段：账户名称、货币类型、初始余额、当前余额、隐藏/显示开关、删除
  - 支持 CRUD 操作
- **分类管理**（收入分类 + 支出分类）：
  - 收入分类：默认 `工资` `奖金` `投资` `其他`，支持添加/编辑/删除/排序
  - 支出分类：默认 `餐饮` `交通` `住房` `娱乐` `购物` `医疗` `教育` `其他`，支持添加/编辑/删除/排序
  - 每个分类可自定义颜色（预设色板选择）

#### Tag 管理
- 全局 Tag 列表（供记账和统计时打标签）
- 支持添加/编辑/删除 Tag
- Tag 字段：名称 + 颜色（预设色板）

---

### 4.3 首页 Tab `/`

**目的**：综合财务状况概览

#### 顶部指标卡（4 个）
| 卡片 | 指标 | 说明 |
|------|------|------|
| 总资产 | 所有账户余额之和 | 数字 + 同比变化百分比 |
| 总收入 | 本月总收入 | 数字 + vs 上月百分比 |
| 总支出 | 本月总支出 | 数字 + vs 上月百分比 |
| 净余额 | 收入 - 支出 | 数字 + vs 上月百分比 |

#### 月度趋势图（折线图）
- X 轴：最近 12 个月
- Y 轴：收入 / 支出 / 净余额
- 两条折线（收入绿色 / 支出红色）+ 净余额柱状图

#### 本月支出分类饼图
- 环形图，中间显示本月总支出
- 各支出分类按比例切片，颜色取自分类自定义色
- 点击切片跳转统计 Tab 对应分类

#### 最近记账记录
- 最近 10 条记账流水
- 列表展示：日期、描述、分类、金额（收入绿/支出红）、Tags

#### 快捷操作
- `+ 记账` 浮动按钮（右下角），点击跳记账 Tab

---

### 4.4 记账 Tab `/bookkeeping`

**目的**：粗粒度月度记账（以月为颗粒度）

#### 月份选择器（顶部）
- 左右切换月份，顶部居中显示 `2024年3月`
- 快速跳转：今日 / 本月 / 上月

#### 月度卡片（主内容）
- 显示当前选中月的以下信息：
  - **月份概览**：总收入、总支出、净余额
  - **收入列表**：可展开，每条记录显示：日期、描述、金额（绿色）、Tags
  - **支出列表**：可展开，每条记录显示：日期、描述、金额（红色）、Tags
  - **转账记录**：账户A → 账户B，金额

#### 添加记账条目（对话框）
- 类型选择：收入 / 支出 / 转账（Tab 切换）
- 公共字段：
  - **日期**：默认今天，可选（date picker）
  - **金额**：必填，数字输入，保留 2 位小数
  - **账户**：下拉选择（从管理页创建的账户列表）
  - **描述**：文本输入（可选）
- 收入/支出专用字段：
  - **分类**：必填，从管理页创建的分类中选择
  - **Tags**：多选，从管理页创建的 Tags 中选择
  - **备注**：文本域（可选）
- 转账专用字段：
  - **源账户** + **目标账户**
  - **金额**
  - **备注**

#### 编辑/删除
- 每条记录右侧操作按钮（编辑 / 删除）
- 删除需二次确认

---

### 4.5 审计 Tab `/audit`

**目的**：检查、核对、修改过往的记账记录

#### 月份筛选
- 年份 + 月份下拉选择，支持快速跳转

#### 审计列表
- 按日期倒序展示所有记账记录（收入/支出/转账混合）
- 每条记录展示：
  - 日期、时间、类型（收入/支出/转账，颜色区分）
  - 金额（收入绿/支出红/转账蓝）
  - 账户、分类
  - Tags（以小徽章展示）
  - 描述/备注
  - **修改时间** + **创建人**（如有多账户场景）
  - 操作按钮：编辑、删除

#### 编辑对话框
- 打开后可修改所有字段
- 提交后更新记录

#### 删除
- 需输入 `DELETE` 确认
- 删除后不可恢复（显示提示）

#### 审计日志（附加功能）
- 记录每次修改的时间、旧值、新值
- 审计日志仅管理员可见（账户所有者）

---

### 4.6 统计 Tab `/statistics`

**目的**：多维度展示财务统计数据

#### 时间范围选择
- 预设：本周 / 本月 / 本季度 / 本年 / 自定义范围
- 自定义：起始日期 + 结束日期

#### 支出分析
- **支出分类饼图**：环形图，颜色取分类色
- **支出分类柱状图**：横向柱状图，各分类金额排序
- **Top 5 支出项**：列表展示最大 5 笔支出

#### 收入分析
- 同上结构，绿色系

#### 收入 vs 支出对比
- 分组柱状图：每月一组，红色（支出）/ 绿色（收入）

#### 收支趋势
- 折线图：最近 12 个月
- 可切换：收入线 / 支出线 / 净余额线

#### Tags 分析
- 选择一个或多个 Tag，展示这些 Tag 的汇总数据
- 饼图 + 列表

#### 账户分析
- 各账户余额排名
- 各账户收支占比

#### 导出
- 导出当前统计数据为 CSV

---

### 4.7 报表 Tab `/reports`

**目的**：生成和归档财务报表

#### 报表生成器
- **报表类型选择**：
  - 资产负债表（BS）
  - 当月损益表（P&L）
  - 当月现金流量表（CF）
  - 月度汇总
  - 季度汇总
  - 年度汇总
- **时间范围**：自动填充当前月/季度/年，支持自定义
- **生成按钮**：点击生成预览

#### 报表预览
- 完整的报表视图，以卡片形式展示
- 格式参考标准财务报表格式，但简化为中文

#### 资产负债表（BS）
```
资产
├── 流动资产
│   ├── 现金及等价物    [所有账户余额之和]
│   └── 其他流动资产    [预留]
├── 非流动资产
│   └── [预留]
─────────────────────────
负债
├── 流动负债           [预留]
└── 非流动负债         [预留]
─────────────────────────
净资产               [资产 - 负债]
```

#### 损益表（P&L）
```
收入
├── 工资收入
├── 投资收入
└── 其他收入           [按分类汇总]
─────────────────────────
支出
├── 餐饮
├── 交通
├── 住房
└── ...                [按分类汇总]
─────────────────────────
净利润              [收入 - 支出]
```

#### 现金流量表（CF）
```
期初现金余额
+ 本月收入
- 本月支出
─────────────────────────
期末现金余额
```

#### 归档功能
- 点击 `归档` 按钮，将当前报表存入归档
- 归档列表（见下方）

#### 归档列表
- 表格展示所有已归档报表
- 字段：报表类型、时间范围、生成日期、文件大小
- 支持查看详情（重新渲染报表）
- 支持删除归档

---

### 4.8 设置 Tab `/settings`

**目的**：用户个性化配置

#### 基本设置
- **语言**：简体中文 / English（默认简体中文）
- **货币符号**：¥ / $ / € / £（默认 ¥）
- **日期格式**：YYYY-MM-DD / DD/MM/YYYY / MM/DD/YYYY（默认 YYYY-MM-DD）
- **时区**：自动检测 + 可手动选择

#### 外观设置
- **主题**：浅色模式（默认）/ 深色模式预留（当前版本仅浅色）
- **侧边栏默认展开**：是 / 否

#### 安全设置
- **修改密码**：当前密码 + 新密码 + 确认密码
- **退出登录**：所有设备（清除 JWT）

#### 数据管理
- **导出所有数据**：导出为 JSON 文件（含加密后的数据）
- **清除所有数据**：二次确认后清除（危险操作）
- **账户删除**：删除账户并清除所有数据（危险操作）

---

## 五、数据模型

### 5.1 用户（User）
```typescript
interface User {
  id: string;              // UUID
  email: string;           // 唯一
  passwordHash: string;    // bcrypt 哈希
  name: string;            // 昵称
  createdAt: Date;
  updatedAt: Date;
}
```

### 5.2 账户（Account）
```typescript
interface Account {
  id: string;
  userId: string;          // 所属用户（外键）
  name: string;
  currency: string;        // 货币代码，如 CNY/USD
  initialBalance: number;   // 初始余额
  hidden: boolean;         // 是否在首页隐藏
  sortOrder: number;
  createdAt: Date;
  updatedAt: Date;
}
```

### 5.3 分类（Category）
```typescript
interface Category {
  id: string;
  userId: string;
  type: 'income' | 'expense';
  name: string;
  color: string;           // HEX 色值，如 #4CAF50
  icon: string;            // 可选，Feather 图标名
  sortOrder: number;
  createdAt: Date;
  updatedAt: Date;
}
```

### 5.4 Tag
```typescript
interface Tag {
  id: string;
  userId: string;
  name: string;
  color: string;           // HEX 色值
  createdAt: Date;
}
```

### 5.5 记账记录（Transaction）
```typescript
interface Transaction {
  id: string;
  userId: string;
  type: 'income' | 'expense' | 'transfer';
  date: string;            // YYYY-MM-DD
  amount: number;          // 金额（正数）
  accountId: string;       // 主账户（收入到账账户 / 支出扣款账户 / 转账源账户）
  destAccountId?: string;  // 转账目标账户（仅 type=transfer）
  categoryId?: string;     // 分类（仅 income/expense）
  tagIds: string[];        // 关联 Tags
  description: string;     // 描述
  remark: string;          // 备注
  createdAt: Date;
  updatedAt: Date;
}
```

### 5.6 报表归档（ReportArchive）
```typescript
interface ReportArchive {
  id: string;
  userId: string;
  reportType: 'BS' | 'PL' | 'CF' | 'MONTHLY' | 'QUARTERLY' | 'YEARLY';
  periodStart: string;     // YYYY-MM-DD
  periodEnd: string;       // YYYY-MM-DD
  content: string;         // JSON 序列化报表数据（加密存储）
  generatedAt: Date;
}
```

### 5.7 设置（UserSettings）
```typescript
interface UserSettings {
  userId: string;
  language: 'zh' | 'en';
  currencySymbol: string;
  dateFormat: 'YYYY-MM-DD' | 'DD/MM/YYYY' | 'MM/DD/YYYY';
  timezone: string;
  sidebarExpanded: boolean;
}
```

---

## 六、后端 API 设计（FastAPI）

### 6.1 认证接口
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 登录，返回 JWT |
| POST | `/api/auth/logout` | 登出 |
| POST | `/api/auth/forgot-password` | 忘记密码 |
| GET | `/api/auth/me` | 获取当前用户信息 |

### 6.2 账户管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/accounts` | 获取所有账户 |
| POST | `/api/accounts` | 创建账户 |
| PUT | `/api/accounts/:id` | 更新账户 |
| DELETE | `/api/accounts/:id` | 删除账户 |

### 6.3 分类管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/categories` | 获取所有分类 |
| POST | `/api/categories` | 创建分类 |
| PUT | `/api/categories/:id` | 更新分类 |
| DELETE | `/api/categories/:id` | 删除分类 |

### 6.4 Tag 管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tags` | 获取所有 Tags |
| POST | `/api/tags` | 创建 Tag |
| PUT | `/api/tags/:id` | 更新 Tag |
| DELETE | `/api/tags/:id` | 删除 Tag |

### 6.5 记账
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/transactions` | 获取记账列表（支持分页、筛选） |
| POST | `/api/transactions` | 创建记录 |
| PUT | `/api/transactions/:id` | 更新记录 |
| DELETE | `/api/transactions/:id` | 删除记录 |

### 6.6 统计
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/statistics/overview` | 首页概览数据 |
| GET | `/api/statistics/by-category` | 按分类统计 |
| GET | `/api/statistics/by-tag` | 按 Tag 统计 |
| GET | `/api/statistics/monthly-trend` | 月度趋势 |

### 6.7 报表
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/reports/bs` | 生成资产负债表 |
| GET | `/api/reports/pl` | 生成损益表 |
| GET | `/api/reports/cf` | 生成现金流量表 |
| GET | `/api/reports/summary` | 生成汇总报表 |
| GET | `/api/reports/archives` | 获取归档列表 |
| POST | `/api/reports/archives` | 归档报表 |
| GET | `/api/reports/archives/:id` | 查看归档详情 |
| DELETE | `/api/reports/archives/:id` | 删除归档 |

### 6.8 设置
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/settings` | 获取用户设置 |
| PUT | `/api/settings` | 更新用户设置 |
| PUT | `/api/settings/password` | 修改密码 |
| DELETE | `/api/settings/account` | 删除账户 |

---

## 七、安全与加密

### 7.1 密码
- 使用 `bcrypt` 哈希密码，前端不存储明文

### 7.2 认证 Token
- 使用 `python-jose` 生成 JWT
- Token 有效期：7 天（可刷新）
- 存储在 localStorage（前端）
- 每次 API 请求携带 `Authorization: Bearer <token>`

### 7.3 数据加密
- **数据库层**：所有敏感字段（description、remark 等文本字段）使用 AES-256-GCM 加密后存储
- 加密密钥：`secret_key` 从环境变量或配置文件读取
- 每个字段加密时生成唯一 IV（初始化向量），存储格式：`iv:ciphertext:tag`
- 账户余额、金额等数值字段是否加密可选（建议不加密以支持计算，可加密存储在应用层）

### 7.4 数据隔离
- 后端所有查询必须附加 `userId` 过滤
- JWT token 中嵌入 `userId`，每次请求自动注入
- 无 `userId` 参数的接口一律 403

---

## 八、项目目录结构

```
FinKit/
├── backend/                      # 后端
│   ├── app/
│   │   ├── main.py               # FastAPI 入口
│   │   ├── config.py             # 配置管理
│   │   ├── database.py           # 数据库连接
│   │   ├── models/              # SQLAlchemy 模型
│   │   │   ├── user.py
│   │   │   ├── account.py
│   │   │   ├── category.py
│   │   │   ├── tag.py
│   │   │   ├── transaction.py
│   │   │   ├── report_archive.py
│   │   │   └── settings.py
│   │   ├── schemas/             # Pydantic 序列化模型
│   │   │   ├── auth.py
│   │   │   ├── account.py
│   │   │   ├── category.py
│   │   │   ├── tag.py
│   │   │   ├── transaction.py
│   │   │   ├── statistics.py
│   │   │   ├── report.py
│   │   │   └── settings.py
│   │   ├── routers/            # API 路由
│   │   │   ├── auth.py
│   │   │   ├── accounts.py
│   │   │   ├── categories.py
│   │   │   ├── tags.py
│   │   │   ├── transactions.py
│   │   │   ├── statistics.py
│   │   │   ├── reports.py
│   │   │   └── settings.py
│   │   ├── services/           # 业务逻辑
│   │   │   ├── auth_service.py
│   │   │   ├── report_service.py
│   │   │   └── statistics_service.py
│   │   ├── utils/              # 工具函数
│   │   │   ├── security.py     # JWT + 加密
│   │   │   └── crypto.py       # AES 加密/解密
│   │   └── middleware/         # 中间件
│   │       └── auth.py         # JWT 验证中间件
│   ├── requirements.txt
│   └── run.py                  # 启动脚本
│
├── frontend/                    # 前端
│   ├── public/
│   ├── src/
│   │   ├── assets/             # 静态资源
│   │   ├── components/        # 公共组件
│   │   │   ├── common/         # Button, Input, Modal, Card, Badge...
│   │   │   ├── layout/         # AppSidebar, AppHeader, AppLayout
│   │   │   └── charts/         # LineChart, PieChart, BarChart
│   │   ├── composables/        # Vue Composables
│   │   │   ├── useAuth.ts
│   │   │   ├── useApi.ts
│   │   │   └── useToast.ts
│   │   ├── pages/
│   │   │   ├── auth/           # Login, Register
│   │   │   ├── admin/          # 管理页
│   │   │   ├── home/           # 首页
│   │   │   ├── bookkeeping/    # 记账页
│   │   │   ├── audit/          # 审计页
│   │   │   ├── statistics/     # 统计页
│   │   │   ├── reports/        # 报表页
│   │   │   └── settings/      # 设置页
│   │   ├── router/
│   │   │   └── index.ts       # 路由配置
│   │   ├── stores/             # Pinia stores
│   │   │   ├── auth.ts
│   │   │   ├── accounts.ts
│   │   │   ├── categories.ts
│   │   │   ├── tags.ts
│   │   │   ├── transactions.ts
│   │   │   └── settings.ts
│   │   ├── styles/
│   │   │   ├── globals.css     # 全局 CSS + CSS Variables
│   │   │   └── animations.css  # 动画
│   │   ├── types/
│   │   │   └── index.ts       # TypeScript 类型
│   │   ├── App.vue
│   │   └── main.ts
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   └── package.json
│
└── README.md
```

---

## 九、开发规范

### 9.1 提交规范（Conventional Commits）
```
feat: 新功能
fix: 修复 bug
refactor: 重构
style: 样式调整
docs: 文档
test: 测试
chore: 构建/工具
```

### 9.2 Git 分支
```
main          # 主分支（稳定）
dev           # 开发分支
feat/xxx      # 功能分支
fix/xxx       # 修复分支
```

### 9.3 前端规范
- 组件文件 PascalCase：`AccountCard.vue`
- Composables 以 `use` 开头：`useAuth.ts`
- Store 以 `use` 开头：`useAuthStore.ts`
- CSS 类名使用 BEM 或语义化命名
- 所有 API 请求通过 `useApi.ts` composable 封装

### 9.4 后端规范
- 路由函数命名：`router_xxx`
- 服务层函数命名：`ServiceName.method()`
- 所有输入参数使用 Pydantic Schema 验证
- 数据库操作使用 async + SQLAlchemy 2.0 async

---

## 十、实施优先级（Phase）

### Phase 1 — 骨架（MVP）
1. 项目初始化（FastAPI 后端 + Vue3 前端）
2. 认证模块（注册/登录/JWT）
3. 账户管理 + 分类管理（CRUD）
4. 记账页（创建/编辑/删除记录）
5. 首页（概览指标 + 趋势图）

### Phase 2 — 完善
6. Tag 管理
7. 审计页（查看/编辑/删除历史记录）
8. 统计页（多维度图表）
9. 数据加密（字段级加密）

### Phase 3 — 报表
10. 报表生成（BS / PL / CF）
11. 报表归档功能
12. 导出功能（CSV/JSON）

### Phase 4 — 打磨
13. 设置页完善
14. 深色模式（预留）
15. i18n（中文/English）
16. 响应式移动端适配

---

## 十一、参考来源

- **UI 设计语言**：AutoManga 设计系统（`prompt-前端设计语言（用作参考）.md`）
- **功能参考**：ezBookkeeping v1.1.1（`ezbookkeeping-v1.1.1-windows-x64/`）
- **图表参考**：ezBookkeeping 桌面端的 Vue Chart.js 实现
- **配色参考**：ezBookkeeping 移动端 Framework7 配色（`--accent: #c67e48` 保留为高亮强调色）

---

> 本文档由 AI 基于 ezBookkeeping 功能 + AutoManga 设计语言生成。
> 保留所有设计决策，Agent 可直接按此规范开发。
