"""Adapt an OTLP/JSON trace export into an offline Incident Atlas case."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SENSITIVE_ATTRIBUTE = re.compile(
    r"(?:email|user\.id|card|cvv|password|passwd|token|secret|authorization|cookie|address)",
    re.IGNORECASE,
)
SOURCE_URL = "https://github.com/open-telemetry/opentelemetry-demo"


def _attribute_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    for kind in ("stringValue", "boolValue", "intValue", "doubleValue", "bytesValue"):
        if kind in value:
            return value[kind]
    if "arrayValue" in value:
        return [_attribute_value(item) for item in value["arrayValue"].get("values", [])]
    if "kvlistValue" in value:
        return _attributes(value["kvlistValue"].get("values", []))
    return value


def _attributes(values: Any) -> dict[str, Any]:
    if not isinstance(values, list):
        return {}
    result = {}
    for entry in values:
        if not isinstance(entry, dict) or not isinstance(entry.get("key"), str):
            continue
        key = entry["key"]
        if SENSITIVE_ATTRIBUTE.search(key):
            continue
        result[key] = _attribute_value(entry.get("value"))
    return result


def _time_from_nanos(value: Any, field: str) -> datetime:
    try:
        nanoseconds = int(value)
        return datetime.fromtimestamp(nanoseconds / 1_000_000_000, tz=UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        raise ValueError(f"OTLP span is missing a valid {field}") from None


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _read_documents(raw: bytes) -> list[dict[str, Any]]:
    try:
        document = json.loads(raw)
        if isinstance(document, dict):
            return [document]
    except json.JSONDecodeError:
        pass
    documents = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            document = json.loads(line)
        except json.JSONDecodeError:
            raise ValueError(f"Input is not valid OTLP/JSON at line {line_number}") from None
        if not isinstance(document, dict):
            raise ValueError(f"OTLP/JSON line {line_number} must contain an object")
        documents.append(document)
    if not documents:
        raise ValueError("Input contains no OTLP/JSON documents")
    return documents


def adapt_otlp_trace_json(
    raw: bytes,
    *,
    case_id: str,
    incident_id: str,
    incident_start: datetime,
    demo_version: str,
    scenario_name: str,
    window_minutes: int = 15,
) -> dict[str, Any]:
    """Return evidence-only case data; ground-truth labels are never inferred."""
    if incident_start.tzinfo is None or incident_start.utcoffset() is None:
        raise ValueError("incident_start must include a timezone")
    if not 5 <= window_minutes <= 15:
        raise ValueError("window_minutes must be between 5 and 15")
    if not all(
        value.strip() for value in (case_id, incident_id, demo_version, scenario_name)
    ):
        raise ValueError("case, incident, Demo version, and scenario names are required")

    start = incident_start.astimezone(UTC)
    window_start = start - timedelta(minutes=5)
    window_end = start + timedelta(minutes=window_minutes)
    items: list[dict[str, Any]] = []
    signals_imported: set[str] = set()
    for document in _read_documents(raw):
        for resource_spans in document.get("resourceSpans", []):
            if not isinstance(resource_spans, dict):
                continue
            resource = _attributes((resource_spans.get("resource") or {}).get("attributes", []))
            service_name = str(resource.get("service.name") or "unknown_service")
            for scope_spans in resource_spans.get("scopeSpans", []):
                if not isinstance(scope_spans, dict):
                    continue
                for span in scope_spans.get("spans", []):
                    if not isinstance(span, dict):
                        continue
                    trace_id = str(span.get("traceId") or "")
                    span_id = str(span.get("spanId") or "")
                    if not trace_id or not span_id:
                        continue
                    began = _time_from_nanos(span.get("startTimeUnixNano"), "startTimeUnixNano")
                    ended = _time_from_nanos(span.get("endTimeUnixNano"), "endTimeUnixNano")
                    if ended < began:
                        raise ValueError("OTLP span endTimeUnixNano precedes startTimeUnixNano")
                    if began < window_start or began > window_end:
                        continue
                    status = (span.get("status") or {}).get("code", "STATUS_CODE_UNSET")
                    status_name = {
                        "0": "UNSET",
                        "1": "OK",
                        "2": "ERROR",
                        "STATUS_CODE_UNSET": "UNSET",
                        "STATUS_CODE_OK": "OK",
                        "STATUS_CODE_ERROR": "ERROR",
                    }.get(str(status), "UNSET")
                    evidence_id = f"otel-trace-{trace_id}-span-{span_id}"
                    items.append(
                        {
                            "evidence_id": evidence_id,
                            "kind": "span",
                            "observed_at": _iso(began),
                            "payload": {
                                "trace_id": trace_id,
                                "span_id": span_id,
                                "parent_span_id": span.get("parentSpanId") or None,
                                "service_name": service_name,
                                "operation": str(span.get("name") or "unknown operation"),
                                "started_at": _iso(began),
                                "duration_ms": round((ended - began).total_seconds() * 1000, 3),
                                "status": status_name,
                                "attributes": _attributes(span.get("attributes", [])),
                            },
                        }
                    )
                    signals_imported.add("traces")

        for resource_metrics in document.get("resourceMetrics", []):
            if not isinstance(resource_metrics, dict):
                continue
            resource = _attributes((resource_metrics.get("resource") or {}).get("attributes", []))
            service_name = str(resource.get("service.name") or "unknown_service")
            for scope_index, scope_metrics in enumerate(resource_metrics.get("scopeMetrics", [])):
                if not isinstance(scope_metrics, dict):
                    continue
                for metric_index, metric in enumerate(scope_metrics.get("metrics", [])):
                    if not isinstance(metric, dict):
                        continue
                    metric_name = str(metric.get("name") or "unknown_metric")
                    unit = str(metric.get("unit") or "1")
                    for family in ("gauge", "sum", "histogram", "exponentialHistogram"):
                        data_points = (metric.get(family) or {}).get("dataPoints", [])
                        for point_index, point in enumerate(data_points):
                            if not isinstance(point, dict):
                                continue
                            timestamp = point.get("timeUnixNano") or point.get(
                                "startTimeUnixNano"
                            )
                            try:
                                observed_at = _time_from_nanos(timestamp, "timeUnixNano")
                            except ValueError:
                                continue
                            if observed_at < window_start or observed_at > window_end:
                                continue
                            if "asDouble" in point or "asInt" in point:
                                value = float(point.get("asDouble", point.get("asInt")))
                            elif point.get("count") and point.get("sum") is not None:
                                value = float(point["sum"]) / float(point["count"])
                            elif point.get("max") is not None:
                                value = float(point["max"])
                            else:
                                continue
                            attributes = _attributes(point.get("attributes", []))
                            stable_key = json.dumps(
                                [service_name, metric_name, _iso(observed_at), scope_index,
                                 metric_index, point_index],
                                separators=(",", ":"),
                            )
                            evidence_id = "otel-metric-" + hashlib.sha256(
                                stable_key.encode()
                            ).hexdigest()[:32]
                            items.append(
                                {
                                    "evidence_id": evidence_id,
                                    "kind": "metric",
                                    "observed_at": _iso(observed_at),
                                    "payload": {
                                        "metric_name": metric_name,
                                        "service_name": service_name,
                                        "value": value,
                                        "unit": unit,
                                        "statistic": family,
                                        "labels": attributes,
                                    },
                                }
                            )
                            signals_imported.add("metrics")
    if not items:
        raise ValueError("No trace spans fall inside the requested incident window")

    items.sort(key=lambda item: (item["observed_at"], item["evidence_id"]))
    return {
        "dataset_schema": "incident-atlas-evidence-case-v1",
        "case_id": case_id,
        "incident_id": incident_id,
        "incident_start": _iso(start),
        "evidence_window": {"start": _iso(window_start), "end": _iso(window_end)},
        "evidence": items,
        "source_provenance": {
            "kind": "imported_otel_demo_capture",
            "source_project": "OpenTelemetry Demo",
            "source_url": SOURCE_URL,
            "demo_version": demo_version,
            "scenario_name": scenario_name,
            "capture_sha256": hashlib.sha256(raw).hexdigest(),
            "transport": "OTLP/JSON trace export",
            "signals_imported": sorted(signals_imported),
            "sensitive_attribute_policy": "drops common identity, credential, and payment keys",
            "ground_truth_included": False,
        },
        "labeling_status": "unlabeled_review_required",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="OTLP/JSON trace export")
    parser.add_argument("--output", required=True, type=Path, help="Evidence-only JSON case")
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--incident-id", required=True)
    parser.add_argument("--incident-start", required=True, help="ISO 8601 timestamp with timezone")
    parser.add_argument(
        "--demo-version", required=True, help="Pinned OpenTelemetry Demo release or commit"
    )
    parser.add_argument(
        "--scenario-name", required=True, help="For example, recommendationCacheFailure"
    )
    parser.add_argument("--window-minutes", type=int, default=15)
    args = parser.parse_args()
    try:
        incident_start = datetime.fromisoformat(args.incident_start.replace("Z", "+00:00"))
        raw = args.input.read_bytes()
        adapted = adapt_otlp_trace_json(
            raw,
            case_id=args.case_id,
            incident_id=args.incident_id,
            incident_start=incident_start,
            demo_version=args.demo_version,
            scenario_name=args.scenario_name,
            window_minutes=args.window_minutes,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(adapted, indent=2, sort_keys=True) + "\n")
    except (OSError, ValueError) as exc:
        print(f"OTLP import failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"Wrote {len(adapted['evidence'])} spans; "
        f"capture sha256={adapted['source_provenance']['capture_sha256']}; "
        "case remains unlabeled and is not public runtime data."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
