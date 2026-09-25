#!/usr/bin/env bash
# Idempotent bootstrap for the PopSight Cloud Agent environment.
# Prepares the FastAPI backend (Python venv) and the Vite frontend (npm),
# then seeds a local .env so secrets can be added without editing tracked files.
set -euo pipefail

cd "$(dirname "$0")/.."

# Safety net: the default image may lack venv support. The snapshot already has
# it, but keep this so a from-scratch install still succeeds.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y python3.12-venv
fi

# Backend: isolated virtualenv with pinned requirements.
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

# Frontend: install node dependencies against the committed lockfile.
npm install

# Local environment file (gitignored). Empty keys run PopSight in demo mode with
# a SQLite database; fill in GEMINI_API_KEY / SERPAPI_API_KEY to unlock live LLM,
# RAG, and the SerpAPI-backed discovery pipelines.
if [ ! -f .env ]; then
  cp .env.example .env
fi

echo "PopSight environment ready."
