---
title: BAZSPARK
emoji: 🔥
colorFrom: red
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
tags:
  - fire-safety
  - nfpa-72
  - bim
  - fastapi
  - react
  - revit
---

# BAZSPARK — Safety-Critical Fire Alarm Engineering Platform

Full-stack deployment: **React 18 + Vite + Tailwind 4** frontend served alongside a **FastAPI** backend on a single origin (no CORS issues).

## Architecture
- **Frontend** (served at `/`) — React 18 + TypeScript + Tailwind v4, built into static assets in the Docker image.
- **Backend** (served at `/api/*`) — FastAPI with full RBAC, X-API-Key auth, and 30+ routers covering NFPA 72, NEC, SOLAS, IMO.
- **Single origin** — the FastAPI app mounts `StaticFiles` at `/assets` and falls back to `index.html` for all non-API routes (SPA routing).

## Auto-Sync
This Space is **automatically synced** from GitHub on every push to `main`:
- Source of truth: [github.com/ahmdelbaz28-ux/revit](https://github.com/ahmdelbaz28-ux/revit)
- Sync workflow: `.github/workflows/sync-to-hf.yml`
- Only runtime files are mirrored (backend/, fireai/, frontend/, parsers/, etc.)
- Docs, tests, skills/, deploy/ configs are excluded (not needed at runtime)

## Endpoints
- `/` — BAZspark React frontend (Login → Dashboard → Room Design → Marine → AI Agent → Reports)
- `/api/health` — Backend health check (public)
- `/api/v1/auth/login` — Authenticate with FireAI API key
- `/api/v1/projects` — Project CRUD (X-API-Key required)
- `/api/v1/qomn/*` — NFPA 72 engineering calculations (smoke/heat spacing, battery, voltage drop, detector placement)
- `/api/v1/facp/*` — FACP selection and compliance (NFPA 72 §10.6.10, UL 864)
- `/api/v1/marine/*` — SOLAS / IMO / MED ship design pipeline
- `/api/v1/environment/*` — Weather, geocode, hazmat, severe weather
- `/api/v1/projects/:id/reports/*` — Compliance reports (PDF/DXF/Excel)

## Maintainer
Eng. Ahmed Elbaz — [bazspark.com](https://bazspark.com)
