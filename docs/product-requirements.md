# Product requirements

**Status:** Step 1 blueprint  
**Reviewed:** 2026-11-22

## Product goal

Incident Atlas is a public, recruiter-friendly demonstration of how an AI-assisted incident investigation can combine timelines, service dependencies, metrics, logs, and traces into ranked, evidence-linked hypotheses. Visitors should complete the full investigation journey without creating an account or entering an API key. The product must describe every cause as a hypothesis, show uncertainty, and stop at an explicit human-approved simulation boundary.

The demo uses fixed, synthetic incidents. A live AI run is a fresh model inference over a versioned synthetic evidence snapshot; it is not a connection to a production environment or a live telemetry feed.

## Visitor journey

1. Open the landing page and choose **Explore incidents**. The landing page states that the data is synthetic and distinguishes stored replays from live AI analysis.
2. Browse a short incident list and pick one of three incidents. Each card shows severity, affected service, incident window, and whether a replay is available.
3. Open the incident workspace. Read the incident summary and symptom markers, then inspect the chronological timeline and service dependency graph.
4. Open telemetry panels for metrics, logs, or traces. Selecting a chart point or span filters the other panels to the same time range and service where the data supports it. Each item has a stable evidence ID and source metadata.
5. Choose either **View stored replay** or **Run live AI investigation**. The replay returns a previously saved result and makes no model call. Live analysis asks the backend to build a fresh, bounded investigation from the same synthetic incident snapshot.
6. Review ranked hypotheses. Each hypothesis shows a plain-language explanation, uncertainty label, evidence that supports it, evidence that weakens it, and a safe next check. Evidence links open the matching timeline or telemetry item.
7. Review a suggested mitigation as a proposal. Select **Approve simulated mitigation**, read a confirmation that no service will be changed, and confirm. The app records a simulation approval event and displays “Simulation recorded; no system was changed.”
8. Visit **Methodology & evaluation** to see how synthetic scenarios are generated, what “live” means in this demo, and how the system is evaluated.

## Pages and routes

| Route | Purpose | Main interactions |
|---|---|---|
| `/` | Explain the product and provide a direct start point. | Explore incidents; choose a featured incident; open methodology. |
| `/incidents` | Browse the reproducible incident catalogue. | Filter by severity/service; open an incident; restore all filters. |
| `/incidents/:incidentId` | Incident investigation workspace. | Inspect summary, timeline, dependency graph, metrics/logs/traces; select replay or live run; open linked evidence. |
| `/investigations/:investigationId` | Review one persisted live run. | Expand hypotheses and evidence; return to incident; approve a simulated mitigation. |
| `/methodology` | Explain data provenance, live-versus-replay labels, limitations, evaluation, and safety boundary. | Follow links to scenario definitions and evaluation plan. |
| Not-found / service-error view | Recover from an invalid route or unavailable API. | Return to incidents; retry read; use a stored replay if live analysis is unavailable. |

The hosted app needs no login. The live model credential is held only by the API host. If no server credential is configured or the model provider is unavailable, live analysis is visibly disabled with a reason and the replay remains usable.

## Public demo promise

Without signing in or supplying an API key, a recruiter can:

- browse all three incidents and inspect their timeline and service graph;
- inspect deterministic metric charts, logs, and trace spans;
- open a stored replay with ranked, linked hypotheses;
- follow evidence links from a hypothesis back to telemetry;
- approve a mitigation **simulation** and see its recorded outcome;
- compare the replay label with a live AI result when the hosted demo has its server-side model credential enabled; and
- read methodology and evaluation notes.

Visitors never need to submit their own incident data. No UI action can modify an external service.

## User interactions and requirements

- Incident list filters update the visible list, URL query parameters, and empty-state explanation.
- Timeline items, service nodes, chart points, logs, and spans share incident-relative timestamps and evidence identifiers.
- Evidence links focus and announce the target panel for keyboard and screen-reader users.
- Replay is a one-click read path. Its result banner reads **STORED REPLAY · saved result · no model call** and shows the original replay timestamp and fixture version.
- A live result banner reads **LIVE AI ANALYSIS · model ran now · synthetic fixture telemetry** and shows run time, model identifier, prompt version, and evidence snapshot hash. It must never be labeled as live telemetry.
- The approval dialog says the action is simulated, identifies the selected mitigation, and requires an explicit confirmation. The response clearly states that no production system was contacted or changed.
- Visitors can inspect input evidence and outputs; hidden chain-of-thought is neither requested nor displayed. The displayed explanation is a concise rationale tied to evidence references.

## Loading, empty, and error states

| State | Required behavior |
|---|---|
| Initial page/data load | Show page-level skeletons with accessible loading announcements. Do not render fabricated incident values as if they came from the API. |
| Telemetry panel loading | Keep the incident header and other panels usable; show a panel-local spinner and selected filter window. |
| Empty telemetry filter | Explain that this time range/service has no fixture signal and provide a clear reset. |
| Live run pending | Disable duplicate submission, show “Preparing evidence snapshot” then “Waiting for model response” only when the backend reports those actual phases; otherwise use one neutral “Investigation running” state. |
| Live model unavailable/timeout | Preserve the incident page, show a concise retryable error, and provide **View stored replay**. Never silently substitute a replay for a requested live run. |
| Rate limit | Explain the temporary limit and retry delay. Replay and read-only incident browsing remain available. |
| Read API unavailable | Show cached page shell only if the browser has a clearly marked cached response; otherwise show an error and retry action. No false “healthy” status. |
| Not found | Identify the missing incident/run and link back to the catalogue. |
| No hypothesis above confidence policy | Show an explicit “Evidence is insufficient to rank a likely cause” result, cite what was checked, and recommend the next read-only check. |
| Approval write failure | Keep the dialog open, explain that no approval was recorded, and allow retry. Do not show success optimistically. |

## Quality and accessibility requirements

- Meet WCAG 2.2 AA target for the built interface, with keyboard navigation, visible focus, chart text alternatives, semantic headings, reduced-motion support, and contrast-safe status colors.
- Fit common laptop and mobile viewport sizes. On narrow screens, panels become stacked sections and the service graph offers a text dependency list.
- All displayed timestamps include timezone context; fixture times are clearly labeled as simulated.
- Deep links preserve the incident and investigation identifiers without requiring session state.
- The product must remain useful if the live model is turned off.

## Out of scope for Step 1 and initial product

- Production telemetry ingestion, cloud account access, arbitrary user-uploaded logs, shell access, automated remediation, paging, organization accounts, and production-grade incident management.
- Claiming calibrated probabilities or a proven root cause from model output.
- Real execution of a mitigation or any connection from a mitigation button to an external system.
- Building or deploying the app during Step 1.
