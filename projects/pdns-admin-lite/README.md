# pdns-admin-lite

A minimal web UI for managing DNS records on a **PowerDNS Authoritative** server, built as a proof of concept: a **FastAPI** backend acting as a thin adapter over the PowerDNS REST API, and a **Vue 3 + Vite** frontend served by nginx, all wired together behind a **Caddy** edge proxy with docker-compose.

> Scope note: **zones are managed by Ansible** (or whatever provisions your DNS server) — this UI only reads zones and creates/updates/deletes records (rrsets).

---

## Key Features

- 📋 Zone list and per-zone record table (SOA and other unmanaged types shown read-only)
- ✏️ Create, edit, and delete record sets (`A`, `AAAA`, `CNAME`, `TXT`, `MX`, `SRV`, `NS`, `PTR`) via PowerDNS `rrsets` PATCH calls
- 🔌 Backend is a thin async adapter (`httpx`) over the PowerDNS REST API — no database of its own
- 🐳 Self-contained dev stack: Caddy edge (only published port) → nginx static frontend + FastAPI backend + a disposable, seeded demo PowerDNS
- 🧪 Backend test suite mocks PowerDNS with `respx` — no live DNS server needed in CI

## Architecture

```text
browser ──► caddy :8080 ──► /api/* ──► backend (FastAPI :8000) ──► PowerDNS API :8081
                       └──► /*     ──► frontend (nginx :80, static Vue bundle)
```

| Path | What it is |
|---|---|
| `backend/` | FastAPI app (Poetry, Python 3.13): `core/pdns.py` PowerDNS client, `api/routes.py` endpoints, `tests/` |
| `frontend/` | Vue 3 + Vite + TypeScript SPA, multi-stage Dockerfile ending in `nginx:alpine` |
| `pdns/seed.sh` | One-shot seeder creating the demo `example.test.` zone through the same API calls Ansible uses |
| `docker-compose.yml` | Dev stack: `edge`, `frontend`, `backend`, `pdns`, `pdns-seed` |
| `Caddyfile` | Edge routing: `/api/*` → backend, everything else → frontend |

## Prerequisites

- Docker + docker compose (for the full stack)
- Optional, for local development outside containers: Python ≥ 3.13 with [Poetry](https://python-poetry.org/), Node.js ≥ 24

## Quick Setup

```bash
cd projects/pdns-admin-lite
cp .env.example .env
docker compose up --build
```

Then open <http://localhost:8080> — the demo `example.test.` zone is already seeded. The API is reachable through the same origin:

```bash
curl http://localhost:8080/api/zones
curl http://localhost:8080/api/zones/example.test.
```

## Configuration

All settings come from environment variables (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `EDGE_PORT` | `8080` | Host port published by the Caddy edge |
| `PDNS_API_URL` | `http://pdns:8081/api/v1` | PowerDNS API endpoint the backend talks to |
| `PDNS_API_KEY` | `changeme-dev-key` | PowerDNS API key (`X-API-Key` header) |

### Pointing at a real PowerDNS

Set the real endpoint and key in `.env` (never commit it — it is gitignored):

```bash
PDNS_API_URL=http://10.0.0.12:8081/api/v1
PDNS_API_KEY=<real-key>
```

Then start only the app services, skipping the demo DNS server:

```bash
docker compose up --build --no-deps edge frontend backend
```

> Note: the edge listens on plain HTTP for this POC. Switching Caddy to TLS is a two-line `Caddyfile` change (`tls internal` or a real hostname with ACME).

## Local development

Backend (REPL-friendly, auto-reload):

```bash
cd backend
poetry install
poetry run pytest -v                 # unit tests, PowerDNS mocked with respx
poetry run uvicorn main:app --reload # http://localhost:8000, needs a reachable PDNS_API_URL
```

Frontend (Vite dev server proxies `/api` to `http://localhost:8000`, so no CORS setup is needed):

```bash
cd frontend
npm install
npm run dev     # http://localhost:5173
npm run build   # type-check (vue-tsc) + production bundle
```

Tip: `docker compose up pdns pdns-seed` gives you a disposable seeded PowerDNS on the compose network; add `ports: ["8081:8081"]` to the `pdns` service locally if you want to reach it from the host.

## API surface

| Endpoint | Maps to (PowerDNS) | Notes |
|---|---|---|
| `GET /api/health` | — | liveness, used by the Docker healthcheck |
| `GET /api/zones` | `GET /zones` | id, name, kind, serial |
| `GET /api/zones/{zone_id}` | `GET /zones/{id}` | includes rrsets, sorted by name/type |
| `POST /api/zones/{zone_id}/records` | `PATCH` (`REPLACE`) | 409 if the rrset already exists |
| `PUT /api/zones/{zone_id}/records` | `PATCH` (`REPLACE`) | replaces the whole rrset |
| `DELETE /api/zones/{zone_id}/records?name=&type=` | `PATCH` (`DELETE`) | deletes the rrset |

Record names may be relative (`web`), `@` for the zone apex, or FQDNs — the backend canonicalizes them to the trailing-dot form PowerDNS expects. There are intentionally no zone create/delete endpoints.

## License

This project is licensed under a **No-Commercial License** — see the repository root [LICENSE](../../LICENSE) file.
