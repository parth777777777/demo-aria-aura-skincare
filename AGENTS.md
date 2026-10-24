# Repository notes

- This is a two-part app, not a root-managed workspace: run frontend commands from `frontend/`; backend code and Python requirements are under `backend/`.
- Frontend scripts are in `frontend/package.json`: `npm run dev`, `npm run lint` (Oxlint), and `npm run build`. Use `npm ci` there when dependencies need installing; `package-lock.json` is committed. No frontend test script is defined.
- Backend dependencies are pinned in `backend/requirements.txt`. Local run command from `backend/` (after installing requirements and setting up its environment): `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`. There is currently no documented test command/config.
- Backend secrets/config belong in `backend/.env`; `.env.example` documents variables. Keep Gemini credentials backend-only; `VITE_*` variables are browser-visible and must never contain secrets.
- Read the actual project specs before changing domain behaviour: `docs/aura_skincare_functional_requirements.md`, `docs/aura_tool_call_list.md`, and `docs/mock-orders.md`. Older-looking paths mentioned inside those docs (for example `docs/functional-requirements.md`) do not exist in this repository.
- The intended boundary is Gemini Live for conversation and requesting tools, with FastAPI/Python as the trusted owner of order data and policy/action validation. Keep model-callable tools allowlisted and do not trust model-supplied order status, eligibility, or totals.
- The mock fixtures are the three documented `ORD-101`–`ORD-103` orders. They are static demo data; backend actions must re-check current status and keep changes consistent for the session.
