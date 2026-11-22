"""Offline-only evaluation helpers. The API and live investigation path never import this module."""

from typing import Any

from incident_atlas.fixtures import (
    LABELS_PATH,
    SCENARIOS_PATH,
    build_evidence_items,
    load_json,
    parse_dt,
    sha256_json,
)
from incident_atlas.rules import evaluate_rules

RULE_TO_LABEL = {
    "cache-miss-after-deploy": "cache_key_version_mismatch",
    "pool-saturation-with-stable-query": "inventory_connection_leak",
    "slow-downstream-with-retries": "upstream_payment_gateway_latency",
}


def evaluate_fixture_dataset() -> dict[str, Any]:
    scenarios_payload = load_json(SCENARIOS_PATH)
    labels_payload = load_json(LABELS_PATH)
    labels = {case["incident_id"]: case for case in labels_payload["cases"]}
    outcomes: list[dict[str, Any]] = []
    reciprocal_ranks: list[float] = []
    evidence_recalls: list[float] = []

    for scenario in scenarios_payload["scenarios"]:
        label = labels[scenario["id"]]
        items = build_evidence_items(scenario)
        result = evaluate_rules(scenario["id"], parse_dt(scenario["started_at"]), items)
        predicted = [
            RULE_TO_LABEL[rule["rule_id"]]
            for rule in result["fired_rules"]
            if rule["rule_id"] in RULE_TO_LABEL
        ]
        expected = label["expected_primary_label"]
        rank = predicted.index(expected) + 1 if expected in predicted else None
        reciprocal_ranks.append(1 / rank if rank else 0.0)
        cited_ids = {
            evidence_id for rule in result["fired_rules"] for evidence_id in rule["evidence_ids"]
        }
        expected_support = set(label["expected_supporting_evidence_ids"])
        recall = (
            len(cited_ids & expected_support) / len(expected_support) if expected_support else 1.0
        )
        evidence_recalls.append(recall)
        outcomes.append(
            {
                "case_id": label["case_id"],
                "incident_id": scenario["id"],
                "expected_primary_label": expected,
                "predicted_ranked_labels": predicted,
                "top_1_correct": bool(predicted and predicted[0] == expected),
                "reciprocal_rank": rank and 1 / rank or 0.0,
                "fired_rule_ids": [rule["rule_id"] for rule in result["fired_rules"]],
                "cited_evidence_ids": sorted(cited_ids),
                "expected_supporting_evidence_recall": round(recall, 4),
                "abstained": not bool(predicted),
            }
        )

    count = len(outcomes)
    correct = sum(outcome["top_1_correct"] for outcome in outcomes)
    return {
        "dataset_version": labels_payload["label_version"],
        "dataset_sha256": sha256_json(labels_payload),
        "fixture_version": scenarios_payload["fixture_version"],
        "case_count": count,
        "metrics": {
            "top_1_accuracy": round(correct / count, 4) if count else 0.0,
            "mean_reciprocal_rank": round(sum(reciprocal_ranks) / count, 4) if count else 0.0,
            "mean_expected_support_evidence_recall": round(sum(evidence_recalls) / count, 4)
            if count
            else 0.0,
            "abstention_rate": round(sum(outcome["abstained"] for outcome in outcomes) / count, 4)
            if count
            else 0.0,
        },
        "cases": outcomes,
    }
