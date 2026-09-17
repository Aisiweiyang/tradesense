# TradeSense

[![CI](https://github.com/Aisiweiyang/tradesense/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Aisiweiyang/tradesense/actions/workflows/ci.yml)

**中文 | [English](README.en.md)**

**AI foreign-trade inquiry, follow-up, product matching & quotation assistant**

---

# TradeSense（英文版 / English Edition）

**AI assistant for foreign-trade inquiries, customer follow-up, product matching and quoting**

Built for individuals and small teams starting out in foreign trade: product data scattered across Excel files, inquiries arriving via email/WhatsApp/web forms, limited business English, uncertainty about what to ask next, and missed quotation terms. TradeSense is the salesperson's **co-pilot** — it helps understand customers, organize requirements, find products, surface risks, draft replies, calculate quotes and track follow-ups. **Every important commitment (formal quotes, outgoing replies) requires human confirmation** — the system never sends anything automatically.

## ✨ Core capabilities

| Capability | Description |
| --- | --- |
| 📩 Multi-channel inquiries | Manual paste, email (IMAP), WhatsApp Cloud API, website form + chat widget, generic webhook (n8n/Zapier/Make). Without credentials, clearly-labeled **simulated connectors** are used — never fake "connected" states |
| 🧩 Multi-round requirement state | Every field tracks current value / history / confidence / source message; supports revisions, negations, "no preference", contradictions and human locks — locked fields are never auto-overwritten |
| 📊 Inquiry completeness | No opaque scores: explicit confirmed / missing lists and the exact reasons a formal quote cannot be issued yet |
| 🎯 Two-stage product matching | Recall (synonyms + full-text) → deterministic reranking (configurable weights); hard-condition failures are excluded with a **visible reason** |
| ❓ Smart clarification | One primary question per round + secondary list, each with a "why ask this" explanation (regulatory/quote-blocking > conflicts > information gain > preferences) |
| 💰 Deterministic quoting | Computed from tier pricing + packaging/printing/logistics/insurance/duty; every line shows its data source. Internal cost / suggested / customer / approved prices are strictly separated — **human approval makes it formal** |
| 🚢 Document workbench | Shipments, document upload & extraction (page-level evidence), cross-document consistency rules, exception queue, chase emails (see docs/18) |
| 💼 Supplier comparison & quote sheets | Multi-supplier comparison ranking, merged quote sheet PDF export (internal cost never leaks), fixed four-role approval matrix (see docs/19) |
| 🤖 AI Intake | Auto-extract requirements from emails/attachments: AI proposes (with verbatim evidence), state machine adjudicates, locked fields stay locked (see docs/23) |
| 📈 Sales funnel | Nine-stage funnel (new inquiry → won): reached, step conversion, median stage dwell time (right-censored), auto-recorded on create/quote/win (see docs/20) |
| 📚 Knowledge base | Shared trade knowledge (certifications/compliance/practice); cite entries in reply drafts with provenance (see docs/20) |
| 💱 Exchange rates | Manually maintained currency pairs (no external API); cross-currency quotes convert automatically and state the source (see docs/20) |
| ✉️ Reply drafts | 10 scenarios × 3 tones, English body with Chinese parallel text, fact provenance and a human-confirmation checklist |
| 🔔 Follow-up reminders | Due today, overdue, quoted-no-reply, long silence, high intent, incomplete data — every suggestion with its reason |
| 🛡️ Safety boundaries | Org isolation, PBKDF2 passwords, audit log, upload limits, AI output whitelisting, never auto-send |

## 🚀 Quick start

```bash
# Windows (one-click)
scripts\start_dev.bat

# macOS / Linux
bash scripts/start_dev.sh
```

The script automatically: creates a Python venv → installs dependencies → initializes the database (Alembic migration + demo data) → starts backend & frontend → opens the browser.

- Frontend: http://127.0.0.1:5173
- Backend API: http://127.0.0.1:8001 ｜ OpenAPI docs: http://127.0.0.1:8001/docs
- **Demo accounts**: `demo@tradesense-demo.cn` / `demo1234` (owner) · `member@tradesense-demo.cn` / `demo1234` (member, limited approvals)

To use different ports, set `TRADESENSE_BACKEND_PORT` and `TRADESENSE_FRONTEND_PORT` before starting. The Vite proxy follows the backend port automatically, so no source edit is required.

### Manual setup

```bash
# Backend
cd backend
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt        # Windows
.venv/Scripts/python scripts/init_db.py              # migration + demo data
.venv/Scripts/python -m uvicorn app.main:app --port 8001

# Frontend (new terminal)
cd frontend
npm install
npm run dev                                          # http://127.0.0.1:5173
```

### Docker

```bash
docker compose up --build
# Frontend http://localhost:5173 (nginx proxies /api to the backend)
```

## 🧪 Tests

```bash
cd backend && .venv/Scripts/python -m pytest   # 254 tests: unit + API + scenarios + isolation + funnel/KB/FX/insights
cd frontend && npx vitest run                  # 36 tests: components + i18n + API client + pages
cd frontend && npx playwright test             # 3 browser E2E flows (services must be running)
```

## 🖼️ Screenshots

![Analytics dashboard with sales funnel](docs/phase1-screenshots/07-analytics.png)

![Knowledge base](docs/phase1-screenshots/11-knowledge.png)

More under [docs/phase1-screenshots/](docs/phase1-screenshots/).

## ❓ FAQ

**Do I need an AI API key?**
No. Every core flow works without AI (deterministic mode); AI is optional for summarizing/polishing and its output always needs human confirmation.

**Where is my data?**
A single SQLite file by default (`backend/data/`, auto-created); PostgreSQL is supported (see docs/03). All business data is organization-isolated.

**Will the system send emails on my behalf?**
Never. Quotes need human approval and reply drafts must be approved then sent manually.

**Port already in use?**
Set `TRADESENSE_BACKEND_PORT` / `TRADESENSE_FRONTEND_PORT` before starting (see docs/02).

## 📁 Repository layout

```
TradeSense (外贸询盘助手)/
├── backend/                 FastAPI + SQLAlchemy 2 + Alembic (Python 3.13)
│   ├── app/
│   │   ├── models/          30+ business tables, all org-scoped
│   │   ├── services/        requirement-state engine, matching, clarification,
│   │   │                    quoting, drafts, connectors, AI adapter, doc rules
│   │   ├── api/routes/      REST API (unified errors / pagination / RBAC)
│   │   └── seed/            demo data (42 products / 20+ inquiries / 10 scenarios)
│   ├── data/                SQLite files (auto-created at runtime, not committed)
│   ├── alembic/             database migrations
│   ├── scripts/             backend management commands (init_db.py)
│   └── tests/               pytest suite
├── frontend/                React 18 + TypeScript + Vite + Tailwind
│   ├── src/pages/           19 pages (Chinese UI, English toggle)
│   └── e2e/                 Playwright end-to-end flows
├── docs/                    22 documents (Chinese; index below)
│   └── phase1-screenshots/  UI acceptance screenshots
├── scripts/                 cross-cutting dev tools (start scripts, page capture)
├── logs/                    dev logs (runtime only, not committed)
└── docker-compose.yml
```

## 📖 Documentation

Documentation is maintained in Chinese under [`docs/`](docs/) (20 files). Quick guide:

| Document | Content |
| --- | --- |
| [docs/01-新手快速开始.md](docs/01-新手快速开始.md) | Getting started — paste your first inquiry |
| [docs/02-本地启动.md](docs/02-本地启动.md) | Manual setup / env vars / FAQ |
| [docs/03-Docker部署.md](docs/03-Docker部署.md) | Docker Compose / PostgreSQL production mode |
| [docs/04-产品数据导入.md](docs/04-产品数据导入.md) | CSV/Excel import: templates, mapping, validation |
| [docs/05-外部渠道接入.md](docs/05-外部渠道接入.md) | Email / WhatsApp / web form / webhook / n8n |
| [docs/06-系统架构.md](docs/06-系统架构.md) | Stack, modules, data flow |
| [docs/07-数据模型.md](docs/07-数据模型.md) | Entities & relationships |
| [docs/08-多轮状态算法.md](docs/08-多轮状态算法.md) | Slot state machine, locks, conflicts, history |
| [docs/09-搜索与排序算法.md](docs/09-搜索与排序算法.md) | Two-stage retrieval, hard filters, weights |
| [docs/10-报价计算.md](docs/10-报价计算.md) | EXW/FOB/CIF/DDP quote build-up & provenance |
| [docs/11-AI安全边界.md](docs/11-AI安全边界.md) | What AI may and may not do; fallback strategy |
| [docs/12-权限与数据隔离.md](docs/12-权限与数据隔离.md) | Org isolation, audit, sanitization |
| [docs/13-测试说明.md](docs/13-测试说明.md) | Test matrix & how to run |
| [docs/14-已知限制.md](docs/14-已知限制.md) | Current limitations |
| [docs/15-后续路线图.md](docs/15-后续路线图.md) | Roadmap |
| [docs/16-最终交付报告.md](docs/16-最终交付报告.md) | Delivery report (phase 1) |
| [docs/17-优化日志.md](docs/17-优化日志.md) | Logged optimization rounds (problem → fix → verification) |
| [docs/18-单证工作台.md](docs/18-单证工作台.md) | Shipments, document verification, exceptions, chase emails |
| [docs/19-比价与报价单.md](docs/19-比价与报价单.md) | Supplier comparison, quote sheets, permission matrix |
| [docs/20-漏斗与知识库.md](docs/20-漏斗与知识库.md) | Sales funnel, knowledge base, exchange-rate priority |
| [docs/21-使用手册.md](docs/21-使用手册.md) | Full user manual: daily workflow, permissions, FAQ |
| [docs/22-项目介绍与开发指南.md](docs/22-项目介绍与开发指南.md) | Project tour: features, code guide, dev & debugging |

## 🔑 Design principles (as implemented)

1. **AI never touches deterministic logic** — prices are computed by code, hard conditions enforced by code; AI only summarizes/polishes and every AI output requires human confirmation.
2. **Humans stay in charge** — every suggestion can be ignored or edited; formal outputs (quotes, replies) require explicit human approval.
3. **Understandable to beginners** — completeness shows reasons, matching shows explanations, quoting shows sources, clarifications show why.
4. **Runs without any credentials** — no AI, no email, no WhatsApp: the full core flow still works (simulated connectors are clearly labeled).

## ⚠️ Disclaimer

System hints (glossary, duty/certification reminders) are business aids only and **do not constitute legal, tax, customs or certification conclusions**. For terms like DDP, verify duty rates and destination compliance with your freight forwarder and professional advisers.

All customers, suppliers, emails, documents and quotes in the repo are **fictional demo data**.

---

中文文档与说明见 [README.md](README.md)。
