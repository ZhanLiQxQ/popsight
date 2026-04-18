# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Hackathon Context

This project is built for **Hack the Coast 2026 (HTC2026) — Prompt 1: AI Product Discovery & Trend Intelligence Tool**.

**Client: Prince of Peace (PoP)** — a CPG distributor with ~800 products across health foods, herbal teas, ginseng, ginger chews, and Tiger Balm. Sells to 100,000+ U.S. retail outlets. PoP's buyers currently find new products manually (trade shows, social media, networks) with no systematic trend scanning.

**Goal:** Help PoP's buying team identify emerging products, ingredient trends, and category shifts before competitors, using publicly available data.

### Hackathon Requirements

**Core Discovery**
- Ingest data from ≥2 public sources (Amazon, Google Trends, social media, FDA databases, trade publications)
- Identify trending products, ingredients, or categories in food, beverage, wellness, or personal care
- Rank/score opportunities by signal strength (recency, growth rate, category relevance, competition level)

**Business Filtering (PoP's sourcing criteria)**
- Shelf life must exceed 12 months
- Ingredients must not appear on FDA restriction lists
- Flag products from countries with high tariff/trade restriction risk
- Categorize by PoP's product categories: dry goods, confections, teas, personal care, health & wellness

**Product Development Angle**
- Identify ingredient trends PoP could apply to its existing lines (ginger, ginseng)
- Example: kombucha trending → suggest kombucha-ginger product; adaptogens trending → suggest ginseng-adaptogen functional snack
- Flag each opportunity as either **"distribute existing product"** or **"develop new PoP-branded product"**

**Output & Usability**
- Results must be understandable and actionable for non-technical buyers
- Each recommendation needs enough context to decide whether to investigate further

## What This Is

PopSight is a multi-agent AI platform for CPG (Consumer Packaged Goods) market research, built for Prince of Peace. It orchestrates several LLM agents (Strategist, MarketCrawler, TrendAnalyst, ProductSleuth, SupplyPartner) to discover trends, products, and suppliers. Users interact via a React workspace UI and a persistent chat interface.

## Commands

**Frontend:**
```bash
npm run dev          # Vite dev server on port 3000
npm run build        # Production build to dist/
npm run lint         # TypeScript type-check (tsc --noEmit)
```

**Backend:**
```bash
npm run dev:backend    # FastAPI with auto-reload on port 8000
npm run start:backend  # Production FastAPI on 0.0.0.0:8000
```

**Full stack (recommended for local dev):**
```bash
docker compose up --build   # Starts backend (8000), frontend (3000), postgres (5432), qdrant (6333)
```

**Python environment:**
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Vite proxies `/api/*` to the backend, so the frontend always talks to `localhost:3000` and no CORS handling is needed in dev.

## Architecture

### Request Flows

**Scan flow** (`POST /api/scan`): Triggers a LangGraph state machine in `backend/graphs.py` — Strategist Init → MarketCrawler → (TrendAnalyst || ProductSleuth || SupplyPartner in parallel) → Strategist Final → Persist. The Gemini LLM uses web search grounding for live market data.

**Chat flow** (`POST /api/chat`): LangGraph retrieves long-term memory → runs a tool-using agent loop → saves messages to DB. LangGraph checkpoints are stored in a separate SQLite file for cross-session state recovery.

**Bootstrap** (`GET /api/bootstrap`): Loads initial data (conversations, memories, scans, agent logs, macro suggestions) for the frontend on page load.

### Key Layers

| Layer | Files | Responsibility |
|-------|-------|----------------|
| API | `backend/app.py` | 5 FastAPI endpoints |
| Orchestration | `backend/graphs.py` | LangGraph scan + chat state machines |
| LLM | `backend/llm.py` | Gemini API wrapper with web search grounding |
| MCP Tools | `backend/mcp_server.py` | 5 agent-accessible tools (scan context, products, memory, history) |
| Persistence | `backend/repository_*.py` | SQLite (local) or PostgreSQL (Docker) behind a common interface |
| Schemas | `backend/schemas.py` | Pydantic models for all API payloads and DB records |
| Frontend | `src/App.tsx`, `src/lib/gemini.ts` | Workspace UI + API client |

### Persistence

`backend/repository_factory.py` selects the backend based on `POPSIGHT_DATABASE_URL`:
- **SQLite** (default): `data/popsight.db` — created automatically
- **PostgreSQL**: Docker Compose target; requires pgvector extension (enabled by `docker/postgres/init/01_extensions.sql`)

9 tables: `scan_sessions`, `trends`, `products`, `manufacturers`, `conversations`, `messages`, `memory_items`, `agent_logs`, `macro_suggestions`.

### Memory Model

- **Short-term**: current scan, selected product, recent messages, LangGraph checkpoints
- **Long-term**: user preferences, supplier notes, strategic decisions stored in `memory_items` (searchable, pinnable via `POST /api/memory`)

## Environment Variables

Copy `.env` to `.env.local` and fill in:

```
GEMINI_API_KEY=                          # Required for LLM (or GOOGLE_API_KEY)
POPSIGHT_DATABASE_URL=                   # PostgreSQL URL; omit to use SQLite
POPSIGHT_DB_PATH=data/popsight.db        # SQLite path (default)
POPSIGHT_SCAN_MODEL=gemini-2.5-flash     # Model for scan agents
POPSIGHT_CHAT_MODEL=gemini-2.5-flash     # Model for chat agent
POPSIGHT_ALLOW_DEMO_MODE=true            # Return mock data when no API key
POPSIGHT_AUTO_BOOTSTRAP_MACROS=false     # Auto-populate macro suggestions on bootstrap
POPSIGHT_QDRANT_URL=http://localhost:6333 # Optional vector DB
```

Demo mode (`POPSIGHT_ALLOW_DEMO_MODE=true`) returns mock data when no API key is set — useful for frontend work.

## Notable Files

- `backend/business_rules.py` — FDA compliance checking for ingredients (2026 ban list)
- `backend/amazon_service.py` — Amazon product lookup (optional, not required for core flows)
- `vite.config.ts` — API proxy config; modify here if backend port changes
