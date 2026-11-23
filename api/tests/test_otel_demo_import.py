import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from incident_atlas.otel_demo_import import adapt_otlp_trace_json

SAMPLE = Path(__file__).parent / "fixtures" / "otel_demo_trace_sample.json"


def test_otel_demo_adapter_is_deterministic_evidence_only_and_redacts_common_pii():
    raw = SAMPLE.read_bytes()
    args = {
        "case_id": "import-test-case",
        "incident_id": "import-test-incident",
        "incident_start": datetime(2025, 3, 1, 12, 0, tzinfo=UTC),
        "demo_version": "test-fixture-only",
        "scenario_name": "recommendationCacheFailure",
    }
    first = adapt_otlp_trace_json(raw, **args)
    second = adapt_otlp_trace_json(raw, **args)

    assert first == second
    assert first["source_provenance"]["capture_sha256"]
    assert first["source_provenance"]["signals_imported"] == ["traces"]
    assert first["source_provenance"]["ground_truth_included"] is False
    assert first["labeling_status"] == "unlabeled_review_required"
    assert "expected_primary_label" not in first
    assert len(first["evidence"]) == 1
    item = first["evidence"][0]
    assert item["kind"] == "span"
    assert item["payload"]["service_name"] == "recommendation"
    assert item["payload"]["duration_ms"] == 25.0
    assert item["payload"]["status"] == "ERROR"
    assert "user.email" not in json.dumps(first)
    assert "visitor@example.invalid" not in json.dumps(first)


def test_otel_demo_adapter_requires_timestamp_and_bounded_window():
    raw = SAMPLE.read_bytes()
    base = {
        "case_id": "case",
        "incident_id": "incident",
        "incident_start": datetime(2025, 3, 1, 12, 0),
        "demo_version": "v1",
        "scenario_name": "scenario",
    }
    with pytest.raises(ValueError, match="timezone"):
        adapt_otlp_trace_json(raw, **base)
    with pytest.raises(ValueError, match="between 5 and 15"):
        adapt_otlp_trace_json(
            raw,
            **{**base, "incident_start": datetime(2025, 3, 1, 12, 0, tzinfo=UTC)},
            window_minutes=60,
        )


def test_otel_demo_adapter_reads_metric_points_and_redacts_sensitive_metric_attributes():
    timestamp = "1740830400000000000"
    payload = {
        "resourceMetrics": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "checkout"}}
                    ]
                },
                "scopeMetrics": [
                    {
                        "metrics": [
                            {
                                "name": "checkout.container.cpu.throttled_ratio",
                                "unit": "1",
                                "gauge": {
                                    "dataPoints": [
                                        {
                                            "timeUnixNano": timestamp,
                                            "asDouble": 0.72,
                                            "attributes": [
                                                {
                                                    "key": "user.email",
                                                    "value": {
                                                        "stringValue": "private@example.invalid"
                                                    },
                                                },
                                                {
                                                    "key": "container.name",
                                                    "value": {"stringValue": "checkout"},
                                                },
                                            ],
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                ],
            }
        ]
    }
    case = adapt_otlp_trace_json(
        json.dumps(payload).encode(),
        case_id="metric-case",
        incident_id="metric-incident",
        incident_start=datetime(2025, 3, 1, 12, 0, tzinfo=UTC),
        demo_version="synthetic-test-only",
        scenario_name="cpu-scenario",
    )
    assert case["source_provenance"]["signals_imported"] == ["metrics"]
    assert len(case["evidence"]) == 1
    point = case["evidence"][0]
    assert point["kind"] == "metric"
    assert point["payload"]["value"] == 0.72
    assert point["payload"]["labels"] == {"container.name": "checkout"}
