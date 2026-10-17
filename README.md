# BuildTrack

Construction project management and site-operations platform. Projects, tasks, workforce, inventory, procurement, reports, and an operations-intelligence layer: Site Assistant, risk rules, material forecasting, budget checks, monitoring, progress evidence, and an Innovation & Safety hub.

| Folder | Stack |
|---|---|
| [`backend/`](backend) | FastAPI · Python 3.11+ · MongoDB (Motor) |
| [`frontend/`](frontend) | React 18 · Vite · Tailwind CSS · JavaScript |

## Quick start

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
```

**Configure `.env`**
- Set `MONGODB_URL` to your MongoDB connection string. MongoDB Atlas free tier is fine.
- Set `MONGODB_DB_NAME`.
- Set `JWT_SECRET_KEY` to a long random value, for example:
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(48))"
  ```

**Create the indexes and the first administrator account.** It asks for the password at the prompt:

```bash
python scripts/setup_database.py --admin-email you@example.com
```

**Run the backend**

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

API docs: http://127.0.0.1:8001/docs

### 2. Frontend

```bash
cd frontend
npm install
copy .env.example .env            # VITE_API_BASE_URL=http://127.0.0.1:8001/api/v1
npm run dev
```

Open http://127.0.0.1:5173 and sign in with the administrator account.

## Roles and permissions

There are seven roles: admin, project manager, site engineer, worker, vendor, client and contractor.

**Access control**
- Access is permission-based and enforced by the backend (`backend/app/core/permissions.py`).
- Users see only the projects they are assigned to. Assign them in **Settings → Access**.
- Extra duties, such as recording payments or receiving deliveries, are granted per user, not through extra roles.

## Site Assistant (AI)

The assistant has three answer modes, set with `AI_PROVIDER` in `backend/.env`:

| `AI_PROVIDER` | Cost | Notes |
|---|---|---|
| `quick` (default) | Free | No AI model. Answers common questions straight from your records |
| `ollama` | Free | A local model through [Ollama](https://ollama.com) rephrases those answers. Install Ollama and run `ollama pull gemma2:2b` |
| `anthropic` | Paid | Claude. Needs `ANTHROPIC_API_KEY` and `AI_ENABLED=true` |

The Overview, risks, forecasts, budget checks and reports do not use AI and are always free.

## Tests

```bash
cd backend && python -m pytest          # in-memory MongoDB, no network
cd frontend && npm test && npm run lint
```

## Configuration reference

All backend settings, with safe defaults, are listed in [`backend/.env.example`](backend/.env.example):
- AI
- Monitoring schedule
- Private uploads
- Optional email and voice calls

Never commit `.env` files.
