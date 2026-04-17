# PopSight Agent Intelligence

This project is now a full-stack sourcing workspace with:

- React + Vite frontend
- FastAPI backend
- LangGraph `1.x` orchestration for scan and chat flows
- LangChain `create_agent` chat runtime
- Google Gemini model integration
- PostgreSQL persistence for scans, messages, memories, and logs (SQLite fallback supported for local-only runs)
- MCP tool server for scan context, memory retrieval, and memory writes

## Architecture

### Main product flows

1. `POST /api/scan`
   - Runs a LangGraph scan flow.
   - Uses Gemini with Google Search grounding to produce structured market results.
   - Persists `scan_sessions`, `products`, `trends`, `manufacturers`, and `agent_logs`.
   - Links the scan to a conversation thread.

2. `POST /api/chat`
   - Runs a LangGraph chat flow.
   - Uses LangChain `create_agent` on top of Gemini.
   - Connects the agent to MCP tools for:
     - current scan retrieval
     - product lookup
     - conversation history retrieval
     - long-term memory search
     - long-term memory persistence
   - Persists user and assistant messages in SQLite.

3. `POST /api/memory`
   - Saves durable long-term memory entries explicitly.

### Memory design

- Short-term memory:
  - current scan
  - selected product/trend/supplier
  - recent conversation turns
  - LangGraph thread checkpoint state

- Long-term memory:
  - confirmed user preferences
  - durable sourcing heuristics
  - supplier notes
  - strategic decisions

- Conversation history:
  - stored separately from long-term memory
  - acts as the audit and recall layer
  - can be promoted into long-term memory selectively

## Data model

Tables:

- `scan_sessions`
- `trends`
- `products`
- `manufacturers`
- `conversations`
- `messages`
- `memory_items`
- `agent_logs`
- `macro_suggestions`

## Environment

Create `.env.local` from `.env.example` and set:

```bash
GEMINI_API_KEY=...
GOOGLE_API_KEY=...
APP_URL=http://localhost:8000
```

`GOOGLE_API_KEY` can be the same value as `GEMINI_API_KEY`.

## Run locally

### Backend

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn backend.app:app --reload --port 8000
```

### Docker (recommended)

```bash
docker compose up --build
```

This brings up:

- `backend` on `http://localhost:8000`
- PostgreSQL (+pgvector) on port `5432`
- Qdrant vector DB on `http://localhost:6333`

Notes:

- `POPSIGHT_AUTO_BOOTSTRAP_MACROS` defaults to `false` in Docker so the app won't implicitly write "starter" data during `/api/bootstrap`.

### Frontend

If you have Node installed globally:

```bash
npm install
npm run dev
```

If not, you can use the project-local runtime this task set up in `.tools/node`:

```bash
PATH="$(pwd)/.tools/node/bin:$PATH" npm install
PATH="$(pwd)/.tools/node/bin:$PATH" npm run dev
```

The frontend proxies `/api/*` to `http://localhost:8000` by default.

## Key files

- `backend/app.py`: FastAPI routes
- `backend/graphs.py`: LangGraph scan/chat orchestration
- `backend/mcp_server.py`: MCP tool server
- `backend/repository.py`: SQLite persistence
- `backend/llm.py`: Gemini integrations
- `src/App.tsx`: product UI
- `src/lib/gemini.ts`: frontend API client
