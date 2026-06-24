# Mizan (ميزان)

AI-powered accounting platform — a virtual accountant for small businesses, accountants, and finance teams. Saudi VAT/ZATCA-aware, bilingual (Arabic + English, RTL).

## Stack

| Layer | Choice |
|-------|--------|
| Frontend | Next.js 14 · TypeScript · Tailwind CSS · next-intl (AR/EN, RTL) |
| Backend | Django 6 · Django REST Framework · PostgreSQL |
| AI | Anthropic Claude (financial assistant + insights) |
| Deploy | Render (backend + Postgres) · Vercel (frontend) · Docker |

## Layout

```
mizan/
├── backend/     Django 6 + DRF API
├── frontend/    Next.js 14 app
├── render.yaml  Render blueprint (backend + Postgres)
└── docker-compose.yml   Local backend + Postgres
```

## Local development

### Backend (Docker — backend + Postgres)

```bash
cp backend/.env.example backend/.env   # fill values
docker compose up --build
# API at http://localhost:8000  ·  health: http://localhost:8000/api/health/
```

### Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev          # http://localhost:3000
```

## Design

The visual source of truth is the Claude Design file `Mizan Platform.dc.html`. Design tokens (colors, type scale, radii) are centralized in `frontend/tailwind.config.ts` — extend there, never per-page one-offs.

## Governance

- Secrets only in `.env` (gitignored); `.env.example` kept current.
- Every PR runs CI: gitleaks + backend (lint/checks/tests) + frontend (lint/build).
- Double-entry must balance; reports must reconcile; Saudi VAT (15%) exact; tenant isolation enforced server-side.
