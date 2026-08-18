# Pokémon TCG Market Predictor

Web application that tracks and predicts Pokémon TCG card prices using the
[pokemontcg.io](https://pokemontcg.io) API.

**Stack:** Python 3.12 · FastAPI · PostgreSQL 16 · SQLAlchemy 2.0 (async) · Docker · AWS

## Quickstart

```bash
cp .env.example .env          # then edit POSTGRES_PASSWORD
docker compose up --build
# liveness:  http://localhost:8000/health
# readiness: http://localhost:8000/health/db
# docs:      http://localhost:8000/docs
```

Without Docker (needs a local Postgres):

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Project layout & ownership

| Path | Purpose | Owner |
|---|---|---|
| `app/main.py` | FastAPI app factory, lifespan, router wiring | Carter (SWE) |
| `app/core/config.py` | Pydantic V2 settings (env-driven) | Carter |
| `app/db/session.py` | Async engine + `SessionDep` DI | Carter |
| `app/db/models.py` | `Set`, `Card`, `PriceHistory` ORM models | Carter |
| `app/schemas/` | Pydantic V2 request/response schemas | Carter |
| `app/api/routes/` | HTTP routes (health now; cards/predict next) | Carter |
| `app/services/ingestion.py` | pokemontcg.io async client / pipeline | Carter |
| `app/ml/predictor.py` | Price-prediction model interface | Carter |
| `app/security/auth.py` | JWT auth contract (fail-closed stub) | **CyberSec** |
| `Dockerfile` | Hardened multi-stage, non-root image | **CyberSec** |
| `docker-compose.yml` | Local stack (hardening flags = CyberSec) | Shared |
| `.github/workflows/security.yml` | Bandit + Trivy CI scanning | **CyberSec** |

## Branch strategy

`main` is protected and deployable; `develop` is the integration branch.
Feature branches cut from `develop`, merge back via PR (CI security scan
must pass):

- `feature/data-ingestion` — Carter: sets/cards/price ingestion pipeline
- `feature/api-routes` — Carter: cards & price-history endpoints
- `feature/ml-integration` — Carter: predictor training + `/predict` route
- `feature/jwt-auth` — CyberSec: JWT issuance/validation, Secrets Manager
- `feature/devsecops-pipeline` — CyberSec: container hardening, CI scanning

## Next steps

1. `alembic init -t async migrations` and generate the first migration from
   `app/db/models.py` (models are Alembic-ready via naming conventions).
2. Ingestion: paginate `/sets` + `/cards`, upsert, snapshot prices daily.
3. Auth: replace the fail-closed stub in `app/security/auth.py`.
