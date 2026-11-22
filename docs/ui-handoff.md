# Step 3 handoff — UI/UX design (historical)

Step 4 replaced the normal fixture reads with the API integration described in [frontend-integration-handoff.md](frontend-integration-handoff.md). This file records the original Step 3 state and its carried-forward gates; read the Step 4 handoff for current behavior and checks.

**Status:** UI implemented on typed fixture adapters. Backend integration remains Step 4 work.  
**Fixture version:** `1.0.0`  
**Reviewed:** 2026-11-22

## Delivered

- React 19, Vite 8, TypeScript 7, and React Router visitor app under `web/`, with an npm lockfile and no external font or API key dependency.
- Overview and searchable incident library for the three planned synthetic cases.
- Incident workspace with symptom summary, timeline filters for changes and alerts, service dependency relationships, metrics chart points, logs, traces, evidence detail, and replay/live choice.
- Replay report with stored provenance, uncertainty, ranked hypotheses, confidence notes, rule baseline, snapshot hash, and direct evidence links.
- Separate mitigation review route with acknowledgment modal and an explicitly local simulation confirmation.
- Methodology page and illustrative loading, empty, timeout, invalid-result, unavailable-service, and partial-data states.
- Async typed client boundary so Step 4 can replace the fixture adapter with API reads while keeping the response shapes and page structure.
- Visual decisions and accessibility/responsive rules in [ui-design.md](ui-design.md).

Fixture adapters import `data/incidents/scenarios.json` and `data/incidents/replays.json`. They do not import `data/evaluation/labels.json`. All three replay reports reference only evidence IDs that exist in their corresponding fixture snapshots. Snapshot IDs and hashes match the values recorded by the Step 2 backend handoff. The rules baseline remains a comparator and the UI never calls its signal labels ground truth.

## Local setup and checks

From a clean checkout with Node.js 20.19+ and npm:

```bash
cd web
npm ci
npm run dev
```

Open the Vite URL printed in the terminal. The app is fixture-only and works without FastAPI, PostgreSQL, sign-in, or a model credential.

Checks run during Step 3:

| Command/check | Result |
|---|---|
| `npm ci --no-audit --no-fund` | Passed with the committed lockfile. |
| `npm run build` | Passed: TypeScript project build and Vite production bundle. |
| `npm run typecheck` | Passed. |
| Replay evidence reference audit against scenario JSON | Passed: cache 6 references, pool 6, gateway 8; no missing IDs. |
| Backend fixture snapshot hash comparison using `api/.venv/bin/python` | Passed: all three hashes match `docs/backend-handoff.md`. |
| Desktop/mobile browser preview | Not completed: the browser tool returned `ERR_CONNECTION_REFUSED` for `127.0.0.1:5173`; local headless Chromium aborted while creating its process socket with `Operation not permitted`. |

The source review covered responsive breakpoints at 950/720/520 px, keyboard tabs and evidence-point actions, focus styling, semantic landmarks, loading/error announcements, textual dependency fallback, and reduced-motion CSS. A WCAG relative-luminance spot check measured core secondary text at 5.3:1 on white and 4.89:1 on the canvas, with selected status pairs at 5.36:1 or higher. Since the rendered page could not be opened in the available browser, desktop/mobile visual fit, a full-page contrast audit, and the complete click-through journey still need a browser preview on a runner that can reach the local server. Do not treat those visual checks as passed.

## Provenance and approval behavior

Browsing is labeled **FIXTURE PREVIEW**. Stored results are labeled **STORED REPLAY**, explicitly say no model call, and expose the original replay timestamp and evidence snapshot. The live action is disabled and explains that no request was made. The mitigation review is a local preview confirmation; it sends no approval route request and changes no external system.

## Step 4 integration tasks

1. Replace `fixtureClient` with an HTTP client implementing the same async interface. Normalize list/detail/timeline/dependency/telemetry envelopes without changing page components.
2. Fetch capabilities and show the live action only when `live_ai_enabled` is true. Keep the stored replay available when live is disabled.
3. Connect replay reads to `GET /api/v1/incidents/{id}/replay` and expose its exact response provenance. Connect live runs to `POST /api/v1/investigations` with an `Idempotency-Key`; show one neutral running state until a response arrives.
4. Parse `application/problem+json` errors and wire timeout, refusal, invalid output, provider unavailable, rate limit, and retry behavior to the existing messages. Never fall back to replay after a failed requested live run.
5. Resolve evidence using the report's `evidence_snapshot_id` and `GET /api/v1/snapshots/{snapshot_id}/evidence/{evidence_id}`. Keep snapshot IDs in evidence links and handle `evidence_not_found` explicitly.
6. Wire simulated approval to the replay/live approval routes only after the confirmation acknowledgment. Display the returned `simulation_only=true` and `external_action_performed=false` values; never add an executor.
7. Add API-origin configuration and exact-origin CORS setup to the hosting environment; preserve the no-key visitor flow.
8. Preview the complete journey at desktop and mobile widths, inspect keyboard focus and contrast, verify the modal and evidence deep links, and fix issues before accepting the visual gate.

## Contract questions and decisions

- **No backend contract change requested.** Snapshot IDs are already returned on reports, and the evidence route accepts the exact snapshot/evidence pair.
- The UI uses a dedicated mitigation route but local-only approval until Step 4 connects both report types to their existing POST routes.
- The backend's live path is one synchronous request, so Step 4 should not invent model phases. Show a neutral “Investigation running” status until the completed response or stable error arrives.
- The API's list/timeline/telemetry envelopes are adapted at the client boundary to the arrays the page components consume. This is a frontend normalization, not a server schema change.
- A true deployment preview and live model credential remain outside Step 3.

## Carried-forward PostgreSQL gate

The Step 2 PostgreSQL acceptance gate remains **UNVERIFIED**. The backend handoff records that 9 PostgreSQL integration cases were skipped because this runner could not create a local Unix socket. Step 3 did not rerun or mark those database checks passed. Run the listed tests against PostgreSQL 15+ before treating migration, idempotent seeding, API/database integration, snapshot immutability, or persisted approvals as verified.
