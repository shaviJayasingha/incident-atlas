# Incident Atlas web

React 19, Vite 8, TypeScript 7, and React Router power the public incident UI. The standard mode reads FastAPI from `/api/v1`; it does not load scenario JSON as a fallback.

## Local API-backed run

Start PostgreSQL, migrate and seed the API as described in [`api/README.md`](../api/README.md). Start FastAPI on `127.0.0.1:8000`, then run the frontend:

```bash
cd web
npm ci
npm run dev
```

Vite proxies `/api/*` to `http://127.0.0.1:8000`, so local browser requests use the same origin. Set `VITE_API_BASE_URL` to the public API base URL ending in `/api/v1` when building for a hosted site. Configure the API's `CORS_ALLOWED_ORIGINS` with that exact site origin. The visitor never supplies a model key; `OPENAI_API_KEY` belongs only in the API host's environment and must never use a `VITE_` variable.

## Development fixture preview

Fixture mode is opt-in and development-only:

```bash
cp .env.development.fixture.example .env.development.local
npm run dev
```

The app labels it **DEV FIXTURE PREVIEW** and keeps its approval record local to the browser. Vite's production build ignores this setting and always uses the API client.

## Checks

```bash
npm test
npm run typecheck
npm run build
```

The Node test runner exercises the API client against mocked contract responses, including pagination, replay provenance, citation resolution, the live capability gate, API problem responses, cancellation, safe read retries, idempotency headers, and acknowledged simulation approvals.
