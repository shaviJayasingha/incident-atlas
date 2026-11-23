# OpenTelemetry Demo telemetry import

This is an offline adaptation path for telemetry captured from a pinned OpenTelemetry Demo release. No Demo capture has been imported into the current evaluation set, and this workflow has not been run against the Demo service stack in the current environment. The public incidents remain authored synthetic fixtures.

The adapter accepts uncompressed, newline-delimited OTLP/JSON output from the Collector file exporter. It imports **traces and numeric metric points** inside an explicitly bounded window. It drops common identity, credential, and payment attribute names, records a SHA-256 hash of the exact source capture, and leaves the result unlabeled. It does not import log bodies. A reviewer must inspect the capture and separately author its ground-truth label before using it in evaluation. The adapted file is an offline evaluation artifact; it is not inserted into the public API database or sent to the live model path.

## Capture a scenario

1. Clone the official [OpenTelemetry Demo repository](https://github.com/open-telemetry/opentelemetry-demo) and check out a release tag or commit. Record the exact ref as `DEMO_VERSION`.
2. Start the Demo using the instructions for that pinned version. The official [feature flag guide](https://opentelemetry.io/docs/demo/feature-flags/) describes scenarios and the local flag UI. For example, `recommendationCacheFailure` exercises a memory-leak scenario; `kafkaConsumerDead` stops the fraud consumer and allows lag to accumulate.
3. In the Collector configuration for that pinned release, add the file exporter to the existing traces and metrics pipelines while preserving their existing exporters:

   ```yaml
   exporters:
     file/incident_atlas:
       path: /var/lib/otel-demo/incident-atlas.jsonl
       format: json
       rotation:
         max_megabytes: 25
         max_backups: 2

   # Append file/incident_atlas to the existing traces and metrics
   # pipeline exporter lists; retain their original destinations.
   ```

   Mount `/var/lib/otel-demo` as a writable volume. Keep exporter compression unset: the [Collector file exporter](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/main/exporter/fileexporter/README.md) writes newline-delimited OTLP JSON by default, and the adapter intentionally does not accept compressed or length-prefixed files. Pin a Collector image version that is compatible with the selected Demo release.
4. Trigger the selected feature flag, keep the scenario within the capture window, and stop collection before preparing the file. Save the active uncompressed `.jsonl` file outside tracked public fixtures until it has been reviewed. Treat the capture as potentially sensitive even though the adapter removes common sensitive attribute keys.

## Adapt a capture

From `api/`, with the locked development environment installed:

```bash
uv run python -m incident_atlas.otel_demo_import \
  --input /secure/captures/incident-atlas.jsonl \
  --output ../data/evaluation/imports/otel-demo-recommendation-cache.json \
  --case-id case-otel-demo-recommendation-cache-v1 \
  --incident-id eval-otel-demo-recommendation-cache-001 \
  --incident-start "$INCIDENT_START" \
  --demo-version "$DEMO_VERSION" \
  --scenario-name recommendationCacheFailure \
  --window-minutes 15
```

`--incident-start` must include a timezone. The adapter keeps spans and metric points from five minutes before that time through the requested 5–15 minute post-start window. It prints the capture hash and evidence count, but never prints the telemetry payload. The generated JSON contains `labeling_status=unlabeled_review_required`, `ground_truth_included=false`, source project, source URL, Demo ref, scenario name, signal types, window, and capture hash. It does not contain an expected cause.

Before adding the case to an evaluation run:

- Inspect the source capture and adapted data for sensitive content. Redact or discard any case that should not be shared.
- Verify the source version, chosen feature-flag scenario, trigger steps, and capture hash from the original file.
- Have an investigator independently document the known cause and expected evidence from the selected Demo scenario's documentation and telemetry. Keep the label in a separate offline evaluation manifest under `data/evaluation/`; do not copy it into the public fixture corpus or model input.
- Add a case-level test that replays the pinned, reviewed adapter output and checks the expected evidence IDs. Record imported Demo cases separately from authored synthetic cases and from genuine model results.

## Verification status

`api/tests/test_otel_demo_import.py` exercises the adapter against a deliberately synthetic OTLP/JSON parser fixture. That test confirms parsing, UTC time conversion, stable hashing, bounded windows, evidence-only output, and common attribute redaction. The fixture is not from the OpenTelemetry Demo. No OpenTelemetry Demo container run, capture, imported evaluation case, or Demo-derived accuracy result has been verified for this release.
