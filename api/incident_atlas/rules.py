from collections import defaultdict
from datetime import datetime
from typing import Any

RULES_VERSION = "rules-v1"


def _metric_groups(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if item["kind"] == "metric":
            groups[item["payload"]["metric_name"]].append(item)
    for points in groups.values():
        points.sort(key=lambda item: (item["observed_at"], item["evidence_id"]))
    return groups


def _before(points: list[dict[str, Any]], incident_start: datetime) -> list[dict[str, Any]]:
    return [point for point in points if point["observed_at"] < incident_start]


def _during(points: list[dict[str, Any]], incident_start: datetime) -> list[dict[str, Any]]:
    return [point for point in points if point["observed_at"] >= incident_start]


def _mean(points: list[dict[str, Any]]) -> float | None:
    if not points:
        return None
    return sum(float(point["payload"]["value"]) for point in points) / len(points)


def _max(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    return max(points, key=lambda point: float(point["payload"]["value"]), default=None)


def _min(points: list[dict[str, Any]]) -> dict[str, Any] | None:
    return min(points, key=lambda point: float(point["payload"]["value"]), default=None)


def evaluate_rules(
    incident_id: str,
    incident_start: datetime,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    """Rank the three transparent scenario rules over one evidence snapshot."""
    metrics = _metric_groups(items)
    fired: list[dict[str, Any]] = []

    hit_points = metrics.get("catalog.cache.hit_ratio", [])
    db_latency = metrics.get("catalog-db.query.duration.p95", [])
    deploy = next(
        (
            item
            for item in items
            if item["kind"] == "timeline" and item["payload"].get("kind") == "deploy"
        ),
        None,
    )
    hit_base = _mean(_before(hit_points, incident_start))
    db_base = _mean(_before(db_latency, incident_start))
    hit_current = _min(_during(hit_points, incident_start))
    db_current = _max(_during(db_latency, incident_start))
    if (
        deploy
        and hit_base is not None
        and db_base
        and hit_current
        and db_current
        and hit_base - float(hit_current["payload"]["value"]) >= 0.50
        and float(db_current["payload"]["value"]) >= db_base * 3
    ):
        fired.append(
            {
                "rule_id": "cache-miss-after-deploy",
                "label": "cache_miss_after_release_signal",
                "evidence_ids": [
                    deploy["evidence_id"],
                    hit_current["evidence_id"],
                    db_current["evidence_id"],
                ],
            }
        )

    pool_points = metrics.get("inventory.db.pool.in_use", [])
    wait_points = metrics.get("inventory.db.pool.wait_ms.p95", [])
    query_points = metrics.get("inventory-db.query.duration.p95", [])
    pool_peak = _max(_during(pool_points, incident_start))
    wait_peak = _max(_during(wait_points, incident_start))
    query_base = _mean(_before(query_points, incident_start))
    query_peak = _max(_during(query_points, incident_start))
    pool_size = (
        float(pool_peak["payload"].get("labels", {}).get("pool_size", 0)) if pool_peak else 0
    )
    if (
        pool_peak
        and wait_peak
        and query_base
        and query_peak
        and pool_size > 0
        and float(pool_peak["payload"]["value"]) / pool_size >= 0.95
        and float(wait_peak["payload"]["value"]) > 500
        and float(query_peak["payload"]["value"]) < query_base * 2
    ):
        fired.append(
            {
                "rule_id": "pool-saturation-with-stable-query",
                "label": "inventory_pool_saturation_signal",
                "evidence_ids": [
                    pool_peak["evidence_id"],
                    wait_peak["evidence_id"],
                    query_peak["evidence_id"],
                ],
            }
        )

    gateway_points = metrics.get("card_gateway.authorize.duration.p95", [])
    timeout_points = metrics.get("payment.authorization.timeout_rate", [])
    retry_points = metrics.get("payment.retry_per_request", [])
    payment_db = metrics.get("payment-db.query.duration.p95", [])
    gateway_peak = _max(_during(gateway_points, incident_start))
    timeout_peak = _max(_during(timeout_points, incident_start))
    retry_peak = _max(_during(retry_points, incident_start))
    payment_db_base = _mean(_before(payment_db, incident_start))
    payment_db_peak = _max(_during(payment_db, incident_start))
    deadline = (
        float(gateway_peak["payload"].get("labels", {}).get("deadline_ms", 0))
        if gateway_peak
        else 0
    )
    if (
        gateway_peak
        and timeout_peak
        and retry_peak
        and payment_db_base
        and payment_db_peak
        and deadline > 0
        and float(gateway_peak["payload"]["value"]) > deadline
        and float(timeout_peak["payload"]["value"]) >= 0.05
        and float(retry_peak["payload"]["value"]) > 0.5
        and float(payment_db_peak["payload"]["value"]) < payment_db_base * 2
    ):
        start_event = next(
            (item for item in items if item["evidence_id"] == "ev-gateway-latency-start"), None
        )
        evidence_ids = [
            gateway_peak["evidence_id"],
            timeout_peak["evidence_id"],
            retry_peak["evidence_id"],
            payment_db_peak["evidence_id"],
        ]
        if start_event:
            evidence_ids.insert(0, start_event["evidence_id"])
        fired.append(
            {
                "rule_id": "slow-downstream-with-retries",
                "label": "downstream_gateway_latency_signal",
                "evidence_ids": evidence_ids,
            }
        )

    fired.sort(key=lambda rule: rule["rule_id"])
    return {
        "version": RULES_VERSION,
        "ranked_labels": [rule["label"] for rule in fired] or ["insufficient_evidence"],
        "fired_rules": fired,
    }
