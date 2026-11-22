# Incident Atlas

Incident Atlas is a no-sign-in incident investigation demo. It provides synthetic OpenTelemetry-shaped incident evidence, stored replay reports, optional evidence-bounded live AI hypotheses, and simulation-only mitigation approvals. Stored replay works without a visitor account or model key. Evaluation labels are kept separate from public runtime data.

## Repository baseline recorded before planning

Inspected before Step 1 on 2026-11-22. The workspace had no application source files, project documentation, dependency manifests, container setup, tests, or local `AGENTS.md`. Its Git metadata mount is read-only, so local Git initialization cannot write `.git/config`; there is no Git remote. The only project-specific instruction supplied for this workspace says it is part of the wider Incident Atlas project and should follow its custom instructions, capabilities, and data. No further local implementation constraints were present.

This is the recorded starting state, not a claim that a GitHub repository already exists. During Step 2, the connected GitHub account had no Incident Atlas repository and the available connector exposed no create-repository action. No remote URL was invented. See [backend handoff](docs/backend-handoff.md).

## Blueprint index

- [Product requirements](docs/product-requirements.md) — visitor journey, page inventory, interactions, states, public demo promise, and non-goals.
- [Architecture](docs/architecture.md) — components, bounded investigation workflow, evidence provenance, uncertainty, and diagrams.
- [API design](docs/api-design.md) — versioned HTTP contracts, request/response shapes, errors, limits, and approval boundary.
- [Data design](docs/data-design.md) — PostgreSQL entities, constraints, telemetry records, snapshots, and retention.
- [Incident scenarios](docs/incident-scenarios.md) — three deterministic synthetic incidents with causes, signals, evidence IDs, and evaluation labels.
- [Deployment plan](docs/deployment.md) — local Compose topology, public hosting, environment variables, operating model, and deployment diagram.
- [Evaluation plan](docs/evaluation-plan.md) — dataset, rules baseline, metrics, test strategy, security, and cost controls.
- [Architecture decisions](docs/decisions.md) — accepted decision records and tradeoffs.
- [Ordered implementation backlog](docs/implementation-backlog.md) — sequenced work and the Step 2 backend completion gate.

## Planned repository layout

```text
docs/                 requirements, architecture, API/data/deploy/evaluation plans
api/                  FastAPI app, migrations, backend README, evaluation runner
web/                  React/Vite static visitor site
data/incidents/       versioned synthetic runtime fixtures and stored replays
data/evaluation/      expected labels and deterministic evaluation variants
infra/                Compose and hosting configuration
```

## Implementation status

Step 1's blueprint is documented above. Step 2 adds the FastAPI/PostgreSQL backend, migrations, deterministic synthetic fixtures and stored replays, optional live investigation, rules evaluation, and focused tests. Step 3 delivers the React/Vite visitor interface. Step 4 connects normal visitor reads and simulated approvals to the backend, with an explicitly labeled development fixture mode. See the [frontend integration handoff](docs/frontend-integration-handoff.md) for exact checks, the browser/DB gate status, and remaining defects.

Step 5 publishes the project source to [GitHub](https://github.com/shaviJayasingha/incident-atlas), adds a PostgreSQL-backed CI workflow, API Docker image, local Compose setup, and Netlify/Render deployment configuration. The hosted CI runner has passed the PostgreSQL 17 migrations, repeated seeding and fixture hashes, all backend tests, frontend checks, Ruff, and API image build. The deployed API/database, genuine live model request, and deployed browser walkthrough remain unverified until the hosting and model services are provisioned and exercised. See [Step 5 handoff](docs/step5-handoff.md) for exact results and blockers.

Step 6 adds focused security and concurrency checks, visitor-scoped append-only approvals, wall-clock provider timeouts, expired rate-event cleanup, a nine-case rules evaluation set, dependency audits, and a local PostgreSQL-backed Playwright journey in CI. See [Step 6 report](docs/step6-report.md) for findings, commit SHA, exact commands and the remaining deployment, database-role, and live-provider gates.

## Web preview (Steps 3–4)

The normal visitor mode reads the FastAPI API and requires no sign-in or visitor model API key. It uses the Vite `/api` proxy locally, and the deployed build takes its API origin from `VITE_API_BASE_URL`. Live analysis is shown only when the backend capability endpoint enables it. Development fixture preview is separate and opt-in.

Requirements: Node.js 20.19 or newer and npm.

```bash
cd web
npm ci
npm run dev
```

Start FastAPI separately using [backend setup](api/README.md), then open the local URL printed by Vite. Set `VITE_API_BASE_URL` for a deployed frontend; never expose `OPENAI_API_KEY` through a `VITE_` variable. To opt into development fixture preview, copy `web/.env.development.fixture.example` to `.env.development.local`; the browser labels that mode and it cannot activate in production builds. Run `npm test`, `npm run typecheck`, and `npm run build`. See [UI design decisions](docs/ui-design.md), [Step 3 handoff](docs/ui-handoff.md), and [Step 4 handoff](docs/frontend-integration-handoff.md).

## Docker Compose

Requirements: Docker Engine with the Compose plugin.

```bash
docker compose up --build
```

Open `http://localhost:5173`. PostgreSQL migrations and runtime fixtures are loaded by the API container. The public journey and approvals work without a model key. To enable live AI locally, set `OPENAI_API_KEY` in the shell or an untracked root `.env`, then set `LIVE_ANALYSIS_ENABLED=true`; never put credentials in a `VITE_*` variable.
