# Evaluation, test, security, and operating-cost plan

**Status:** Current deterministic regression plan; no live model quality result
**Reviewed:** 2026-11-22

## Evaluation status

The repository includes a deterministic rules evaluator and an offline labeled dataset. The API image excludes the evaluation schema data, and live model input is built only from public runtime evidence. Provider tests are mocked; no genuine live model quality result is available. See the current pre-deployment release report for the exact commit and observed CI run.

## Evaluation dataset

The current rules regression set has 12 cases: three authored synthetic base cases, six derived synthetic variants, and three independent authored synthetic cases. The six derived variants and their labels live in `data/evaluation/variants.json`; they do not alter public runtime fixtures or model input. The independent queue-lag, CPU-throttling, and ambiguous shipping-span cases live in `data/evaluation/independent-cases-v1.json`. Eight cases have a positive expected label and four expect abstention. These are small regression cases, not a representative estimate of real incident accuracy. No case is an OpenTelemetry Demo import; the separate [import guide](otel-demo-import.md) documents an executable, currently unverified capture path.

## Rules baseline

The API returns public ranked signal names plus fired rule IDs. The offline evaluator maps rule IDs to expected class labels for scoring; the answer-key values are not exposed by public responses. If no rule fires, the API returns `insufficient_evidence`. Do not claim that the simple baseline is a complete incident system.

### Rule behavior

Implement a transparent, deterministic rules ranker against the exact same frozen evidence packet as the model:

- Cache mismatch: hit ratio drops by ≥50 percentage points after a deploy marker and DB p95 rises ≥3×.
- Pool exhaustion: connection use reaches ≥95%, acquisition wait exceeds 500 ms, and DB query p95 remains <2× baseline.
- Upstream payment slowdown: downstream span exceeds the configured deadline, parent timeout rate rises, retries increase, and local DB p95 remains stable.
- Queue-consumer lag: lag rises against its baseline while producers outpace a sharply reduced consumer rate.
- Checkout CPU throttling: throttling rises materially against its baseline alongside a threefold checkout latency increase.

Rule behavior follows these deterministic conditions:

## Metrics and initial release gates

Report aggregate and per-case metrics; with only twelve authored cases, treat them as regression checks, not a statistically representative benchmark.

| Metric | Definition | Initial gate |
|---|---|---:|
| Labeled top-1 | Fraction of the eight positive cases whose first label matches expected cause. | 8/8 regression cases; do not score abstention cases as positive root-cause predictions. |
| Overall decision accuracy | Positive cases correctly labeled plus abstention cases where no rule fires, divided by all twelve cases. | 12/12 regression cases; never score a forced guess as success when `expected_abstention=true`. |
| Mean reciprocal rank (MRR) | Mean `1 / rank` for the first acceptable label. | ≥0.80. |
| Evidence citation precision | Relevant, real, snapshot-valid cited evidence IDs divided by all cited IDs. | 100% valid IDs; ≥0.90 relevant. |
| Evidence citation recall | Expected key support IDs cited divided by the expected evidence ID set. | 100% on these fixed positives; report per case and preserve missing IDs. |
| Unsupported causal assertion rate | Causal claims without a linked supporting signal divided by all causal claims. | 0 in reviewed release cases. |
| Abstention behavior | Fraction of ambiguous cases where no cause label is emitted. | 4/4 on this fixed regression set. |
| Schema and refusal handling | Provider outcomes that are validated or surfaced as explicit refusal/error without malformed report. | 100%. |
| Latency | End-to-end live request p95 under fixed fixture/model configuration. | ≤18 seconds API deadline; record provider and DB components. |
| Cost | Actual model token cost per successful live run. | Enforce per-run token caps; monthly alert at chosen budget. |
| Baseline comparison | AI versus rules top-1 and evidence recall on same cases. | Publish side-by-side results; do not hide cases where rules perform better. |

Do not describe qualitative confidence as calibrated. If a later version adds numeric confidence, use a larger held-out set and a calibration metric such as Brier score or expected calibration error before public probability wording.

## Test strategy for implementation phases

Step 1 adds no executable tests. Later implementation should add tests in this order:

1. **PostgreSQL-backed integration tests:** repeatable migration/seeding, report evidence resolution, runtime table and column grants, evaluation-label isolation, persisted simulation approvals, live failure modes, rate-cap concurrency, and public replay read behavior.
2. **API and investigation tests:** route schemas, bounded queries, stable errors, bounded live packet, timeout/refusal/malformed output, invalid evidence IDs, mandatory uncertainty, and no arbitrary tool execution.
3. **Evaluation tests:** base, derived, independent, and expected-abstention cases; per-case labels and support evidence recall; importer parser/redaction tests on a synthetic OTLP sample.
4. **Security boundary tests:** no API key in the client bundle or responses; approval only appends simulation rows; no route reaches an external target; prompt-like text inside logs is treated as data.
5. **Browser journey tests:** visitor opens a replay, follows evidence, and approves a simulation without login or a visitor key; live-off and error states remain clear; keyboard and responsive behavior work.
6. **Deployment checks:** API image runtime with PostgreSQL, health and replay paths, configuration guards, and a post-deployment command for exact origin, bundle URL, JSON responses, and browser CORS.

Keep deterministic CI independent of the live model provider. A separate, explicitly budgeted scheduled/manual model evaluation can test live quality; it must not run on every pull request.

## Security boundaries

- Public inputs are limited to fixture IDs, allowed filters/time windows, an idempotency key, and a mitigation selection from a persisted result.
- Database access uses parameterized, read-only statements for evidence gathering. The model cannot send SQL, URLs, tool calls, shell commands, or write requests.
- The only backend write paths are persisted investigation metadata/output and append-only simulation approval. Neither path triggers remediation.
- Prompts treat telemetry strings as untrusted evidence. Synthetic log text may contain instruction-like decoys; they never override system rules.
- Limit request and result sizes, database rows, query duration, inference duration, retry count, and per-IP live rate. Return a replay path after live failures.
- Keep model credentials server-side. Never put them in `VITE_*`, browser storage, source fixtures, exception text, or telemetry attributes.
- Use exact-origin CORS, TLS, least-privilege database role, secure deployment secrets, and dependency lockfiles. Validate provider output before persistence/rendering and escape telemetry/log display text.
- Do not collect visitor account data. Use short-lived HMAC source hashes for rate limits; do not log raw IP or full raw model packets.
- Simulation approval is a UI action recorded as `external_action_performed=false`. No production integration credentials or remediation executor exists.

## Public usage controls

- Three fixed scenarios; no arbitrary file/log upload, no free-form prompts, no arbitrary URLs, and no user-created incident records.
- Serve replay to all visitors without auth or model spend.
- Enable live run only with a server-side provider key and explicit feature flag. Set a hard monthly provider budget, daily alert, request cap, max 3 in-flight requests, max 5 live requests per hashed IP per 15 minutes, and one attempt per run.
- Record token use and provider errors; disable live globally when quota or provider health trips. The capability route drives the UI's live availability label.
- Keep a visible methodology note that the evidence is synthetic and the AI result is advisory.

## Cost model

Monthly total is approximately:

`static hosting + API compute + managed database/storage/transfer + live model token usage`.

Do not use an old price snapshot as an approved budget. Check the current Render and Netlify account quotes, billing setup, plan limits, backup/storage costs, and usage terms when the account owner sets the spending cap. Live inference cost is:

`(input_tokens × current_input_rate + output_tokens × current_output_rate) / 1,000,000`

per run, with rates checked against the configured provider/model at launch. Replays cost no inference tokens. Track monthly live run count, average/max tokens, and spend. A first public quota of 5 live runs per 15 minutes per source hash and a hard provider budget make usage bounded; review this after launch traffic is measured.

## Reporting results

Publish a compact methodology result table with evaluation version/date, source counts, model ID, prompt/schema version, run count, rules baseline scores, any genuine AI scores, failure count, and limitations. Record raw metrics as CI artifacts for reproducibility. Never present a twelve-case score as production readiness or a guarantee of root-cause accuracy. Keep authored synthetic data, imported OpenTelemetry Demo captures, mocked provider tests, and genuine live-model output in separate result categories.

## Current reference sources for cost and integration choices

- [OpenAI Responses API](https://developers.openai.com/api/reference/responses/overview), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses), and [API pricing](https://developers.openai.com/api/docs/pricing).
- [Render pricing](https://render.com/pricing) and [Netlify pricing/usage](https://www.netlify.com/pricing/). Recheck these before Step 2 deployment provisioning and at launch because plans and limits change.
