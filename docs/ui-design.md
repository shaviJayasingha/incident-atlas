# Incident Atlas UI design

**Status:** Step 3 implementation record  
**Scope:** React/Vite fixture preview; backend reads remain for Step 4.

## Product presentation

Incident Atlas is presented as a working incident investigation console rather than a marketing page. The overview leads with the evidence-to-hypothesis loop, then offers the three synthetic cases. Scenario cards state severity, primary service, incident date/time, fixture version, and replay availability. The UI never requires a sign-in or visitor API key.

## Visual system

| Element | Decision |
|---|---|
| Canvas and panels | Cool gray canvas (`#f4f6f8`), white panels, thin blue-gray borders, restrained shadows. |
| Navigation and overview hero | Deep navy (`#132535`) anchors the console and gives the evidence illustration contrast. |
| Evidence and action | Teal marks selected data, evidence links, and the primary action. It does not communicate confidence. |
| Severity and uncertainty | Amber is used for SEV-2 and simulation boundaries; red is reserved for errors and failed validation. |
| Typography | System sans-serif for readable UI copy; system monospace for IDs, hashes, and compact telemetry metadata. No remote font dependency. |
| Spacing and shape | Four/eight-pixel rhythm, 8–12 px panel corners, consistent 13–17 px card padding. |
| Motion | Short hover and focus transitions only; all motion is reduced under `prefers-reduced-motion`. |

Color does not carry status by itself: severity, confidence, source, and approval states all have visible text labels. The design avoids probability-style scores; confidence remains qualitative (`low`, `medium`, `high`) and explicitly uncalibrated.

## Pages and interactions

| Page | Main content and interaction |
|---|---|
| `/` | Product overview, no-key statement, three fixture cards, visitor journey, and prominent fixture/no-model-call label. |
| `/incidents` | Search and severity filters, resettable empty state, and incident cards. |
| `/incidents/:incidentId` | Incident symptom, date-bounded window, service inventory and call relationships, filtered change/alert timeline, telemetry tabs for metrics/logs/traces, evidence detail, and replay/live choices. Live remains disabled with its reason. |
| `/investigations/:reportId` | Persistent **STORED REPLAY** provenance, report/snapshot metadata, ranked hypotheses, confidence notes, uncertainty, baseline comparator, and direct links to cited evidence. |
| `/investigations/:reportId/mitigation` | Proposal review, explicit simulation boundary, acknowledgment dialog, and local preview confirmation. |
| `/methodology` | Synthetic data and evaluation explanation, replay/live distinction, safety boundary, and interactive examples of loading/empty/timeout/invalid/unavailable/partial-data states. The state examples are labeled illustrative, not current API results. |

The three telemetry tabs are a keyboard arrow-key tab set. Metric chart points can be selected with Enter or Space. Timeline filters and the state examples use labeled buttons. Evidence links preserve both the item ID and evidence snapshot ID in the URL; the detail panel displays the exact fixture record and its snapshot metadata. The approval dialog uses a native modal, supports Escape, traps focus, and requires a checked acknowledgment.

## Provenance and service states

- Incident and telemetry pages carry a **FIXTURE PREVIEW** label; browsing them makes no model call.
- Replay reports say **STORED REPLAY**, include `model_call_made: false`, `curated-fixture`, `curated-replay-v1`, zero token usage, original generation time, snapshot ID, and snapshot hash.
- The live action is disabled in Step 3. It does not silently open a replay, submit a request, or label fixture content as a live result.
- Simulated approval is local component state only. The UI states `simulation_only=true` and `external_action_performed=false`, and says no backend write or external action occurred.
- Async client adapters provide loading, retryable read errors, empty results, and partial-panel behavior. Methodology demonstrates timeout and invalid-result messaging without claiming those failures occurred.

## Accessibility and responsive behavior

The app uses a skip link, semantic navigation/main/footer, visible keyboard focus, labeled filters and tabs, announced loading/error regions, readable evidence IDs, accessible chart descriptions, and text-first service relationships. At 950 px the sidebar becomes a compact top navigation; at 720 px workspaces stack; at 520 px cards and panels become single-column and controls wrap. The dependency relationships remain textual at every size. System fonts and CSS are self-contained. A reduced-motion media rule suppresses transitions and smooth scrolling.

## Backend contract fit

The `contracts.ts` interfaces mirror the FastAPI incident, timeline, dependency, telemetry, evidence, replay report, hypothesis, baseline, and approval response fields. `fixtures.ts` adapts the exact scenario and replay JSON into those shapes. The UI makes no backend contract change. Step 4 should map API `items` envelopes to the same types and fetch cited records with `GET /api/v1/snapshots/{snapshot_id}/evidence/{evidence_id}`; citation navigation already carries the snapshot ID. The page design does not assume that a stored replay is live analysis.
