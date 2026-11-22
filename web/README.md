# Incident Atlas web

React 19, Vite 8, TypeScript 7, and React Router power the public incident UI. The standard mode reads FastAPI from `/api/v1`; it does not load scenario JSON as a fallback.

## Local API-backed run

Start PostgreSQL, migrate and seed the API as described in [`api/README.md`](../api/README.md). Start FastAPI on `127.0.0.1:8000`, then run the frontend:

```bash
cd web
npm ci
npm run dev
```

Vite proxies `/api/*` to `http://127.0.0.1:8000`, so local browser requests use the same origin. A production build requires `VITE_API_BASE_URL` to be an absolute HTTPS API base URL ending in exactly `/api/v1`; the build exits before Vite runs if it is unset, relative, HTTP, or malformed. Netlify must receive the real API URL as a build-time variable. In Render, set `PUBLIC_SITE_ORIGIN` to the exact Netlify HTTPS origin and `CORS_ALLOWED_ORIGINS` to that same single origin; production API startup rejects a mismatch. The visitor never supplies a model key; `OPENAI_API_KEY` belongs only in the API host's environment and must never use a `VITE_` variable.

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
VITE_API_BASE_URL=https://api.example.invalid/api/v1 npm run build
npm audit --audit-level=moderate
```

The `.invalid` URL is a safe build-check value only. Do not publish a site built with it.

The Node test runner exercises the API client against mocked contract responses, including pagination, replay provenance, citation resolution, the live capability gate, API problem responses, cancellation, safe read retries, idempotency headers, and acknowledged simulation approvals.

The browser workflow captures screenshots from the local CI API/PostgreSQL journey. The case study labels them as local CI images; they do not imply a public deployment.
