cat > README.md <<'EOF'
# Aura Skincare AI Voice Agent

A browser-based AI customer support agent powered by Gemini Live,
React, and FastAPI.

## Tech Stack

- Frontend: React + Vite + JavaScript
- Backend: Python + FastAPI
- Voice AI: Gemini Live API
- Data: Local mock order and product data

## Prerequisites

- Python 3
- Node.js and npm
- Gemini API key

## Backend Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
