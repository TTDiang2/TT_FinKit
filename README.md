# FinKit (TT_FinKit)

A self-hosted personal wealth management application. Know where your money goes and how it grows.

Part of the **TT** application family — self-hosted, local-first, privacy-respecting tools.

Track every expense, understand your income sources, monitor your investment portfolio, and backtest your trading strategies — all on your own machine.

## 🎯 What is FinKit?

FinKit is a complete personal finance toolkit that helps you:

- **Understand your spending** — Track every yuan with categorization, tags, and location
- **See your cash flow** — Real-time dashboard showing income vs expenses, savings rate, net worth trend
- **Manage investments** — Record buys/sells, track XIRR, visualize portfolio performance
- **Backtest strategies** — Built-in backtesting engine with 70+ factors and pre-built strategies
- **Get AI insights** — News-driven analysis powered by LLM

Your data stays local. No cloud sync, no telemetry, no compromises.

## 📸 Screenshots

### Dashboard & Bookkeeping

| Dashboard | Bookkeeping |
|-----------|-------------|
| ![首页](docs/image/首页-1.png) | ![记账-1](docs/image/记账-1.png) |

| Bookkeeping (cont.) | Statistics |
|---------------------|------------|
| ![记账-2](docs/image/记账-2.png) | ![统计-1](docs/image/统计-1.png) |

### Investment Management

| Portfolio Overview | Backtesting | Research |
|--------------------|-------------|----------|
| ![投资-1](docs/image/投资-1.png) | ![投资-2-回测](docs/image/投资-2-回测.png) | ![投资-3-标的](docs/image/投资-3-标的.png) |

### AI Analysis

| AI Advisor | AI Investment Analysis |
|------------|------------------------|
| ![AI咨询-1](docs/image/AI咨询-1.png) | ![AI咨询-2](docs/image/AI咨询-2.png) |

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11+ + FastAPI |
| **Database** | SQLite + SQLAlchemy 2.0 |
| **Frontend** | Vue 3 + TypeScript + Vite 5 |
| **UI** | Tailwind CSS v3 |
| **Charts** | Chart.js 4 |
| **Auth** | JWT + bcrypt |
| **Encryption** | AES-256-GCM (Fernet) |

## 📦 Installation

### Prerequisites
- Python 3.11+
- Node.js 18+

### Quick Start

```bash
# Backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Edit .env — set SECRET_KEY and ENCRYPTION_KEY
python -m uvicorn app.main:app --reload --port 8100

# Frontend
cd frontend
npm install
npm run dev
```

Open `http://localhost:8100` and register your first account.

### Desktop Build (Windows)

```bash
cd frontend && npm run build && cd ..
cd backend
python scripts/build_release.py --version 0.1.0
# Release package: release/FinKit-v0.1.0.zip
```

## 🔧 Configuration

Copy `backend/.env.example` to `backend/.env`:

```env
SECRET_KEY=your-secret-key-here
ENCRYPTION_KEY=your-encryption-key-here

# Optional: AI services
AI_INFERENCE_API_URL=https://api.openai.com/v1
AI_INFERENCE_API_KEY=sk-...
AI_INFERENCE_MODEL=gpt-4o-mini

# Optional: iFinD (Tonghuashun) for market data
IFIND_USERNAME=
IFIND_PASSWORD=
```

## 🧪 Testing

```bash
cd backend
python -m pytest  # 272 tests
```

## 🔒 Privacy

- **Local-first**: All data stored in SQLite on your machine
- **Encrypted**: Sensitive fields use AES-256-GCM
- **No telemetry**: Nothing leaves your computer
- **Multi-tenant**: Complete user isolation via JWT

## 📝 License

MIT License — see [LICENSE](LICENSE).

---

中文版 README: [README-zh.md](README-zh.md)

*Disclaimer: This is a personal finance tool. Users are responsible for their own data accuracy and investment decisions.*
