# PopSight Agent Intelligence

A full-stack CPG sourcing workspace built for Prince of Peace (PoP), an Asia-forward distributor. Three AI modules work together: product discovery, trend/supply analysis, and a RAG-powered sourcing copilot.

## Stack

- React + Vite frontend
- FastAPI backend
- LangGraph orchestration for scan and chat flows
- Google Gemini (chat + embeddings) or local Ollama for chat
- PostgreSQL + pgvector for persistence
- Qdrant for vector search (RAG over PoP catalog, specs, vendors, inventory, sales history)
- SerpAPI for Google Trends and Amazon product search

## Modules

### Module 1 — Product Fetch (Jane)
`POST /api/pipeline/amazon-ingest`
Fetches Amazon product data via SerpAPI, runs GLiNER NER for compliance signals, and compresses results.

### Module 2 — Discovery Pipeline (Penny)
`POST /api/pipeline/macro-cold-start`

Runs 6 fixed retail lanes through a 7-node LangGraph pipeline. Each lane executes:

| Node | Agent | What it does |
|------|-------|--------------|
| 0 | `fetch_market_signals` | Fetches Google Trends RELATED_QUERIES (rising) per lane |
| 1 | `MacroScout_Agent` | Interprets trend signals; skips lanes with no usable data |
| 2 | `Market_Crawler` | Pulls Amazon top-5-by-reviews per lane via SerpAPI |
| 3 | `NLP_Compressor` | Compresses products; runs FDA check + optional GLiNER NER |
| 4 | `Trend_Analyst_Agent` | Ranks SKUs by traction score |
| 5 | `Supply_Planner_Agent` | Produces actionable sourcing rows |
| 6 | *(summary)* | Generates executive summary in Markdown |

### Module 3 — Sourcing Copilot (Vinny)
`POST /api/scan` + `POST /api/chat`

- **Scan**: Gemini with Google Search grounding produces structured market results (trends, products, manufacturers). Persists to PostgreSQL and links to a conversation thread.
- **Chat**: LangGraph agent with tools for scan context, product lookup, conversation history, long-term memory search/save/delete, and Qdrant RAG over PoP documents.

## Memory design

- **Short-term**: current scan, selected product, recent conversation turns, LangGraph checkpoint state
- **Long-term**: user preferences, sourcing heuristics, supplier notes, strategic decisions (pinned items always surface in chat)
- **RAG**: PoP catalog PDF, item specs, vendor master, inventory, and sales history — chunked and stored in Qdrant

## Environment

Copy `.env.example` to `.env` and fill in:

```bash
# Required
GEMINI_API_KEY=...          # or GOOGLE_API_KEY (same value works for both)
SERPAPI_API_KEY=...

# Models (defaults shown)
POPSIGHT_CHAT_MODEL=gemini-2.5-flash
POPSIGHT_SCAN_MODEL=gemini-2.5-flash

# Optional: use a local Ollama model for chat instead of Gemini
# POPSIGHT_OLLAMA_URL=http://host.docker.internal:11434
# POPSIGHT_CHAT_MODEL=llama3.2:3b
```

## Run with Docker (recommended)

```bash
docker compose up --build
```

This brings up:
- `frontend` on `http://localhost:3000`
- `backend` on `http://localhost:8000`
- PostgreSQL (+pgvector) on port `5432`
- Qdrant on `http://localhost:6333`

### Ingest PoP documents into Qdrant (one-time)

After the stack is up, run the ingestion script to load the PoP catalog, item specs, vendor master, inventory, and sales history into Qdrant for RAG:

```bash
docker compose exec backend python -m backend.ingest
```

This processes ~371 chunks. It uses the Gemini embedding API (free tier: 100 items/min) so takes a few minutes. Re-run any time source data files in `data/` change.

## Run locally (without Docker)

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn backend.app:app --reload --port 8000
```

Requires a running PostgreSQL instance (or leave `POPSIGHT_DATABASE_URL` empty to use SQLite at `data/popsight.db`) and Qdrant at `http://localhost:6333`.

### Frontend

```bash
npm install
npm run dev
```

The frontend proxies `/api/*` to `http://localhost:8000`.

## Key files

- `backend/app.py` — FastAPI routes
- `backend/graphs.py` — LangGraph scan/chat orchestration, memory retrieval, RAG injection
- `backend/ingest.py` — one-time PoP document ingestion into Qdrant
- `backend/vector_store.py` — Qdrant search helper (used by chat on every turn)
- `backend/discovery_graph.py` — Module 2 discovery pipeline
- `backend/llm.py` — Gemini + Ollama client initialization
- `backend/config.py` — all environment variable settings
- `backend/repository_postgres.py` / `repository_sqlite.py` — persistence layer
- `src/App.tsx` — frontend root
