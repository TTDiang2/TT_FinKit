# FinKit

自托管个人财务与投资追踪应用，配备 AI 驱动的智能分析。

## 🌟 功能特性

### 个人财务管理
- **记账功能**: 记录收入、支出、转账，支持分类管理
- **数据看板**: 实时查看净资产、现金流、储蓄率
- **统计分析**: 多维度数据分析，交互式图表展示
- **财务报表**: 生成资产负债表、损益表、现金流量表
- **数据导出**: 支持 CSV/JSON 格式导出

### 投资管理
- **投资组合**: 追踪股票、基金、债券、加密货币等资产
- **交易记录**: 记录买入、卖出、分红、费用等操作
- **收益分析**: XIRR、已实现/浮动盈亏、回撤分析
- **行情更新**: 自动获取市场价格（iFinD 或备用数据源）
- **AI 分析**: 基于新闻的投资洞察，由大语言模型驱动

### 研究与回测
- **标的池**: 精选股票/基金池，包含基本面数据
- **因子库**: 70+ 量化因子，含历史数据
- **策略系统**: 预置策略，支持回测验证
- **信号生成**: 基于策略规则的自动化交易信号
- **风险监控**: 实时投资组合风险评估

### 技术亮点
- **隐私优先**: 本地-first 架构，字段级加密存储 (AES-256-GCM)
- **多用户隔离**: 完整的用户数据隔离，JWT 认证
- **双库设计**: 公开数据（行情、策略）与私有数据（用户交易）分离
- **自托管**: 完全掌控你的数据，无需云端依赖

## 🛠️ 技术栈

| 层次 | 技术选型 | 说明 |
|------|---------|------|
| **后端** | Python 3.11+ + FastAPI | 异步 API 服务 |
| **数据库** | SQLite + SQLAlchemy 2.0 | 本地文件存储 |
| **前端** | Vue 3 + TypeScript + Vite 5 | 现代化单页应用 |
| **UI 框架** | Tailwind CSS v3 | 原子化 CSS 工具类 |
| **图表** | Chart.js 4 + vue-chartjs | 交互式可视化 |
| **认证** | JWT (python-jose) + bcrypt | 安全认证机制 |
| **加密** | Fernet (cryptography) | 字段级数据加密 |

## 📦 安装指南

### 环境要求
- Python 3.11+
- Node.js 18+
- Windows 10+（桌面分发版）

### 后端部署

```bash
cd backend

# 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# 安装依赖
pip install -r requirements.txt

# 复制环境配置模板
copy .env.example .env

# 编辑 .env 文件，配置必要参数
# 必填：SECRET_KEY, ENCRYPTION_KEY

# 启动开发服务器
python -m uvicorn app.main:app --reload --port 8100
```

### 前端部署

```bash
cd frontend

# 安装依赖
npm install

# 运行开发服务器
npm run dev

# 生产构建
npm run build
```

### 桌面打包（Windows）

```bash
# 先构建前端
cd frontend && npm run build && cd ..

# 构建发布包
cd backend
python scripts/build_release.py --version 0.1.0

# 发布包位于 release/FinKit-v0.x.x.zip
```

## 🔧 配置说明

复制 `.env.example` 到 `.env` 并配置：

```env
# 数据库
PUBLIC_DATABASE_URL=
PRIVATE_DATABASE_URL=

# 安全密钥（生产环境必填）
SECRET_KEY=your-secret-key-here
ENCRYPTION_KEY=your-encryption-key-here

# AI 服务
AI_SEARCH_BACKEND=duckduckgo  # duckduckgo 或 tavily
AI_SEARCH_API_KEY=            # 使用 Tavily 时需要
AI_INFERENCE_API_URL=         # OpenAI 兼容 API 端点
AI_INFERENCE_API_KEY=         # 推理 API 密钥
AI_INFERENCE_MODEL=           # 模型名称（如 gpt-4o-mini）

# iFinD（同花顺）凭证
IFIND_USERNAME=
IFIND_PASSWORD=
```

## 🚀 使用说明

1. 启动后端服务
2. 浏览器访问 `http://localhost:8100`
3. 注册新账号
4. 开始记录财务和投资数据

## 📁 项目结构

```
FinKit/
├── backend/                    # 后端应用
│   ├── app/
│   │   ├── main.py            # FastAPI 入口
│   │   ├── config.py          # 配置管理
│   │   ├── database.py        # 数据库连接
│   │   ├── models/            # SQLAlchemy 模型
│   │   ├── routers/           # API 路由
│   │   ├── services/          # 业务逻辑
│   │   ├── schemas/           # Pydantic  schema
│   │   └── utils/             # 工具函数
│   ├── scripts/               # 迁移和工具脚本
│   └── tests/                 # 测试套件（272 个测试）
├── frontend/                   # Vue 3 前端
│   ├── src/
│   │   ├── pages/             # 页面组件
│   │   ├── components/        # 可复用组件
│   │   ├── stores/            # Pinia 状态管理
│   │   └── types/             # TypeScript 类型定义
│   └── package.json
├── docs/                       # 文档
│   ├── SPEC.md               # 原始设计规格
│   ├── INVESTMENTS.md        # 投资模块文档
│   └── RELEASE.md            # 发布指南
├── strategies/                 # 策略实现
├── requirements.txt            # Python 依赖
└── .env.example               # 环境配置模板
```

## 🧪 测试

```bash
cd backend

# 运行所有测试
python -m pytest

# 运行特定测试文件
python -m pytest tests/test_investment_ledger.py

# 生成覆盖率报告
python -m pytest --cov=app --cov-report=html
```

## 🔒 安全特性

- **本地优先**: 所有数据存储在本机，无云端同步
- **字段级加密**: 敏感字段使用 AES-256-GCM 加密
- **JWT 认证**: 安全的会话管理
- **用户隔离**: 用户间数据完全隔离
- **无遥测**: 不收集任何分析或遥测数据

## 📝 许可证

MIT 许可证 - 详见 [LICENSE](LICENSE)

## 🤝 贡献指南

欢迎贡献！请阅读贡献指南并提交 Pull Request。

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: 添加惊人功能'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启 Pull Request

## 🙏 致谢

- [ezBookkeeping](https://github.com/) - 记账功能参考
- [AutoManga](https://github.com/) - UI 设计语言灵感
- [FastAPI](https://fastapi.tiangolo.com/) - 后端框架
- [Vue 3](https://vuejs.org/) - 前端框架

## 📧 支持

如有问题和反馈，请在 GitHub 上开启 Issue。

---

**免责声明**: 本工具仅供个人财务管理参考。用户需对自己的数据准确性和投资决策负责。作者不对任何财务损失承担责任。
