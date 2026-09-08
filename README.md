# FinKit

A self-hosted personal finance and investment tracking application with AI-powered insights.

## 🌟 Features

### Personal Finance Management
- **Bookkeeping**: Track income, expenses, and transfers with categorization
- **Dashboard**: Real-time overview of net worth, cash flow, and savings rate
- **Statistics**: Multi-dimensional analysis with interactive charts
- **Reports**: Generate Balance Sheet, P&L, and Cash Flow statements
- **Data Export**: Export financial data to CSV/JSON

### Investment Tracking
- **Portfolio Management**: Track stocks, funds, bonds, crypto, and other assets
- **Transaction History**: Record buys, sells, dividends, fees, and adjustments
- **Performance Analytics**: XIRR, realized/floating P&L, drawdown analysis
- **Price Updates**: Auto-fetch market prices via iFinD or fallback providers
- **AI Analysis**: News-driven investment insights powered by LLM

### Research & Backtesting
- **Asset Pool**: Curated stock/fund pool with fundamental data
- **Factor Library**: 70+ quantitative factors with historical data
- **Strategy System**: Pre-built strategies with backtesting capabilities
- **Signal Generation**: Automated trading signals based on strategy rules
- **Risk Monitoring**: Real-time portfolio risk assessment

### Technical Highlights
- **Data Privacy**: Local-first architecture with field-level encryption (AES-256-GCM)
- **Multi-tenant**: Complete user isolation with JWT authentication
- **Dual Database**: Public data (market data, strategies) separated from private data (user transactions)
- **Self-hosted**: Run on your own infrastructure, no cloud dependency

## 📸 Screenshots

<!-- Add your screenshots here -->
<!-- Replace the placeholders below with actual screenshots -->

| Dashboard | Bookkeeping | Statistics | Investments |
|-----------|-------------|------------|-------------|
| ![Dashboard](screenshots/dashboard.png) | ![Bookkeeping](screenshots/bookkeeping.png) | ![Statistics](screenshots/statistics.png) | ![Investments](screenshots/investments.png) |

> **Note**: Replace the above image paths with your actual screenshots. See the "Demo Account" section below for guidance on creating sample data.

## 🛠️ Tech Stack

| Layer | Technology | Description |
|-------|-----------|-------------|
| **Backend** | Python 3.11+ + FastAPI | Async API server |
| **Database** | SQLite + SQLAlchemy 2.0 | Local file-based storage |
| **Frontend** | Vue 3 + TypeScript + Vite 5 | Modern SPA |
| **UI Framework** | Tailwind CSS v3 | Atomic CSS utility classes |
| **Charts** | Chart.js 4 + vue-chartjs | Interactive visualizations |
| **Auth** | JWT (python-jose) + bcrypt | Secure authentication |
| **Encryption** | Fernet (cryptography) | Field-level data encryption |

## 📦 Installation

### Prerequisites
- Python 3.11+
- Node.js 18+
- Windows 10+ (for desktop distribution)

### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Copy environment template
copy .env.example .env

# Edit .env with your configuration
# Required: SECRET_KEY, ENCRYPTION_KEY

# Run migrations and start server
python -m uvicorn app.main:app --reload --port 8100
```

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build
```

### Desktop Distribution (Windows)

```bash
# Build frontend first
cd frontend && npm run build && cd ..

# Build release package
cd backend
python scripts/build_release.py --version 0.1.0

# Distribution zip will be in release/FinKit-v0.x.x.zip
```

## 🔧 Configuration

Copy `.env.example` to `.env` and configure:

```env
# Database
PUBLIC_DATABASE_URL=
PRIVATE_DATABASE_URL=

# Security (REQUIRED for production)
SECRET_KEY=your-secret-key-here
ENCRYPTION_KEY=your-encryption-key-here

# AI Services
AI_SEARCH_BACKEND=duckduckgo  # duckduckgo or tavily
AI_SEARCH_API_KEY=            # Required if using Tavily
AI_INFERENCE_API_URL=         # OpenAI-compatible API endpoint
AI_INFERENCE_API_KEY=         # API key for inference
AI_INFERENCE_MODEL=           # Model name (e.g., gpt-4o-mini)

# iFinD (Tonghuashun) Credentials
IFIND_USERNAME=
IFIND_PASSWORD=
```

## 🚀 Usage

1. Start the backend server
2. Open browser to `http://localhost:8100`
3. Register a new account
4. Start tracking your finances and investments

### Demo Account

For demonstration purposes, a demo account is available:

- **Email**: `demo@finkit.example`
- **Password**: `demo123456`

The demo account comes pre-loaded with sample data including:
- 4 accounts (Salary, Savings, Investment, Cash)
- 6 categories (Salary, Bonus, Food, Transport, Housing, Shopping)
- 60+ sample transactions over the past 60 days
- 4 investment products (HS300 ETF, Gold ETF, Money Market Fund, US Tech ETF)
- Investment cash flows

**To create demo data on your own instance:**
```powershell
# Run the seed script (from repository root)
powershell -ExecutionPolicy Bypass -File scripts/seed_demo_data.ps1
```

Or manually create a demo account via the API:
```bash
curl -X POST http://localhost:8100/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@finkit.example","password":"demo123456","name":"Demo User"}'
```

Then use `scripts/seed_demo_data.ps1` to populate sample data.

## 📁 Project Structure

```
FinKit/
├── backend/                    # Backend application
│   ├── app/
│   │   ├── main.py            # FastAPI entry point
│   │   ├── config.py          # Configuration management
│   │   ├── database.py        # Database connections
│   │   ├── models/            # SQLAlchemy models
│   │   ├── routers/           # API routes
│   │   ├── services/          # Business logic
│   │   ├── schemas/           # Pydantic schemas
│   │   └── utils/             # Utility functions
│   ├── scripts/               # Migration and utility scripts
│   └── tests/                 # Test suite (272 tests)
├── frontend/                   # Vue 3 frontend
│   ├── src/
│   │   ├── pages/             # Page components
│   │   ├── components/        # Reusable components
│   │   ├── stores/            # Pinia state management
│   │   └── types/             # TypeScript types
│   └── package.json
├── docs/                       # Documentation
│   ├── SPEC.md               # Original design spec
│   ├── INVESTMENTS.md        # Investment module docs
│   └── RELEASE.md            # Release guide
├── strategies/                 # Strategy implementations
├── requirements.txt            # Python dependencies
└── .env.example               # Environment template
```

## 🧪 Testing

```bash
cd backend

# Run all tests
python -m pytest

# Run specific test file
python -m pytest tests/test_investment_ledger.py

# Run with coverage
python -m pytest --cov=app --cov-report=html
```

## 🔒 Security

- **Local-first**: All data stored locally, no cloud sync
- **Field-level encryption**: Sensitive fields encrypted with AES-256-GCM
- **JWT authentication**: Secure session management
- **User isolation**: Complete data separation between users
- **No telemetry**: No analytics or telemetry collection

## 📝 License

MIT License - see [LICENSE](LICENSE) for details.

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines and submit a pull request.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 🙏 Acknowledgments

- [ezBookkeeping](https://github.com/) - Bookkeeping functionality reference
- [AutoManga](https://github.com/) - UI design language inspiration
- [FastAPI](https://fastapi.tiangolo.com/) - Backend framework
- [Vue 3](https://vuejs.org/) - Frontend framework

## 📧 Support

For questions and support, please open an issue on GitHub.

---

**Note**: This is a personal finance tool. Users are responsible for their own data accuracy and investment decisions. The authors are not liable for any financial losses.
