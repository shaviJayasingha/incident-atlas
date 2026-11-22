# Incident Atlas

Incident Atlas is a no-sign-in incident investigation demo. Visitors can inspect service dependencies and synthetic telemetry, open a stored investigation replay, follow its evidence references, and record a simulated mitigation approval. Approval changes no external system. Stored replays do not call a model and do not require an API key.

**Release status:** The source repository and CI are public. The website, API, and PostgreSQL database have not been deployed. There is no live public demo URL. Hosting remains gated on an approved spending cap and account access. Live AI remains disabled until proxy trust, global request limits, and a genuine provider request are verified.

## Case study and source

- [Portfolio case study and application screenshots](docs/portfolio-case-study.md)
- [GitHub source repository](https://github.com/shaviJayasingha/incident-atlas)
- [Pre-deployment release report](docs/predeployment-release-report.md)
- [Step 6 security and evaluation report](docs/step6-report.md)

## Data provenance and evaluation limits

The three incident scenarios and their stored replays are project-authored, deterministic synthetic data shaped like OpenTelemetry records. They are not imported from the OpenTelemetry Demo and are not real production incidents. The separate answer key is absent from the public API image and live model input.

The rules baseline is measured on three base cases and nine derived regression variants, including expected-abstention cases. Those results describe this small synthetic test set only; they are not real-world incident accuracy. Provider coverage is mocked unless a report explicitly records a genuine live model request. No genuine provider run has been verified for the current release.

## Run locally

With Docker Engine and Compose:

```bash
docker compose up --build
```

Open `http://localhost:5173`. Compose starts PostgreSQL, applies migrations and seeds runtime fixtures in a one-shot bootstrap service, then starts the API and web app. The no-key replay journey works with live AI disabled.

To opt into the separate development fixture preview, copy `web/.env.development.fixture.example` to `web/.env.development.local`. The UI labels this mode **DEV FIXTURE PREVIEW**; it is never selected after an API failure and cannot appear in a production build.

For manual setup, see [API setup](api/README.md) and [web setup](web/README.md). Local checks:

```bash
cd api
uv sync --locked --extra dev --extra observability
uv run pytest -q -rs
uv run ruff check .
uv audit --locked

cd ../web
npm ci
npm test
npm run typecheck
VITE_API_BASE_URL=https://api.example.invalid/api/v1 npm run build
npm audit --audit-level=moderate
```

The production build requires an absolute HTTPS API URL ending in `/api/v1`. The `.invalid` host above is only a safe local build-check value; it is not a deploy target. For Netlify, set `VITE_API_BASE_URL` to the actual API origin at build time. If unset or relative, the build fails instead of silently calling the static site itself.

## Deployment configuration

The planned architecture is Netlify for the static React/Vite site and Render for FastAPI plus PostgreSQL. The Render pre-deploy command migrates and seeds with `MIGRATION_DATABASE_URL`; the API runs with the separate `incident_atlas_runtime` role. Production requires `PUBLIC_SITE_ORIGIN` and `CORS_ALLOWED_ORIGINS` to be the same exact Netlify HTTPS origin. The runtime role cannot access evaluation data or run migrations. Public model calls have a PostgreSQL-backed global cap; `LIVE_ANALYSIS_ENABLED` remains false in the checked-in deployment template.

No paid resources were created. Before provisioning, approve a spending cap and connect the intended hosting account. Then configure the real Netlify API base URL and Render site/CORS origins, verify only actual trusted proxy CIDRs, deploy the API/database, and perform desktop and mobile walkthroughs against the deployed URL. See [deployment setup](docs/deployment.md) and the current [release report](docs/predeployment-release-report.md) for exact gates.

## Project blueprint

- [Product requirements and visitor journey](docs/product-requirements.md)
- [Architecture and workflows](docs/architecture.md)
- [API contracts](docs/api-design.md)
- [PostgreSQL data design](docs/data-design.md)
- [Synthetic incident scenarios](docs/incident-scenarios.md)
- [Evaluation plan](docs/evaluation-plan.md)
- [Architecture decisions](docs/decisions.md)
- [Implementation backlog](docs/implementation-backlog.md)
