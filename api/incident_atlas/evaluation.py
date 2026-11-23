"""Offline-only evaluation helpers. Runtime API and live analysis never import this module."""

from copy import deepcopy
from pathlib import Path
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
    "queue-consumer-lag-with-throughput-gap": "fraud_consumer_lag",
    "checkout-cpu-throttling-with-latency-rise": "checkout_cpu_throttling",
}
EVALUATION_DIR = Path(__file__).resolve().parents[2] / "data" / "evaluation"
VARIANTS_PATH = EVALUATION_DIR / "variants.json"
INDEPENDENT_CASES_PATH = EVALUATION_DIR / "independent-cases-v1.json"


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
                "data_kind": "authored_synthetic_base",
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


def _apply_variant(scenario: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    variant = deepcopy(scenario)
    for change in case["metric_changes"]:
        series = next(
            item for item in variant["metrics"] if item["metric_name"] == change["metric_name"]
        )
        series["values"][change["index"]] = change["value"]
    removed = set(case["remove_timeline_ids"])
    variant["timeline"] = [item for item in variant["timeline"] if item["id"] not in removed]
    return variant


def _independent_items(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = deepcopy(evidence)
    for item in items:
        item["observed_at"] = parse_dt(item["observed_at"])
    return items


def evaluate_expanded_dataset() -> dict[str, Any]:
    """Evaluate base cases, derived variants, and separate authored cases."""
    scenarios_payload = load_json(SCENARIOS_PATH)
    base_labels_payload = load_json(LABELS_PATH)
    variants_payload = load_json(VARIANTS_PATH)
    independent_payload = load_json(INDEPENDENT_CASES_PATH)
    scenarios = {scenario["id"]: scenario for scenario in scenarios_payload["scenarios"]}
    independent_evidence = independent_payload["evidence_by_case"]
    cases: list[tuple[dict[str, Any], str, Any, list[dict[str, Any]], str]] = []
    for label in base_labels_payload["cases"]:
        scenario = scenarios[label["incident_id"]]
        cases.append(
            (
                label,
                scenario["id"],
                parse_dt(scenario["started_at"]),
                build_evidence_items(scenario),
                "authored_synthetic_base",
            )
        )
    for label in variants_payload["cases"]:
        scenario = _apply_variant(scenarios[label["incident_id"]], label)
        cases.append(
            (
                label,
                scenario["id"],
                parse_dt(scenario["started_at"]),
                build_evidence_items(scenario),
                "derived_synthetic_variant",
            )
        )
    for label in independent_payload["cases"]:
        cases.append(
            (
                label,
                label["incident_id"],
                parse_dt(label["incident_start"]),
                _independent_items(independent_evidence[label["case_id"]]),
                label["data_kind"],
            )
        )

    outcomes: list[dict[str, Any]] = []
    reciprocal_ranks: list[float] = []
    evidence_recalls: list[float] = []
    decisions_correct = 0
    labeled_correct = 0
    abstention_cases = 0
    correct_abstentions = 0
    for label, incident_id, incident_start, items, data_kind in cases:
        result = evaluate_rules(incident_id, incident_start, items)
        predicted = [
            RULE_TO_LABEL[rule["rule_id"]]
            for rule in result["fired_rules"]
            if rule["rule_id"] in RULE_TO_LABEL
        ]
        expected = label["expected_primary_label"]
        expected_abstention = label["expected_abstention"]
        abstained = not bool(predicted)
        top_one = bool(expected and predicted and predicted[0] == expected)
        decision_correct = abstained if expected_abstention else top_one
        cited_ids = {
            evidence_id for rule in result["fired_rules"] for evidence_id in rule["evidence_ids"]
        }
        expected_support = set(label["expected_supporting_evidence_ids"])
        recall = (
            len(cited_ids & expected_support) / len(expected_support) if expected_support else None
        )
        if expected_abstention:
            abstention_cases += 1
            correct_abstentions += int(abstained)
        else:
            rank = predicted.index(expected) + 1 if expected in predicted else None
            reciprocal_ranks.append(1 / rank if rank else 0.0)
            evidence_recalls.append(recall or 0.0)
            labeled_correct += int(top_one)
        decisions_correct += int(decision_correct)
        outcomes.append(
            {
                "case_id": label["case_id"],
                "incident_id": incident_id,
                "data_kind": data_kind,
                "expected_primary_label": expected,
                "predicted_ranked_labels": predicted,
                "top_1_correct": top_one,
                "decision_correct": decision_correct,
                "expected_abstention": expected_abstention,
                "abstained": abstained,
                "fired_rule_ids": [rule["rule_id"] for rule in result["fired_rules"]],
                "cited_evidence_ids": sorted(cited_ids),
                "expected_supporting_evidence_recall": (
                    round(recall, 4) if recall is not None else None
                ),
                "notes": label["notes"],
            }
        )

    count = len(outcomes)
    source_counts = {
        data_kind: sum(outcome["data_kind"] == data_kind for outcome in outcomes)
        for data_kind in sorted({outcome["data_kind"] for outcome in outcomes})
    }
    dataset_version = (
        f"{variants_payload['dataset_version']}+{independent_payload['dataset_version']}"
    )
    return {
        "dataset_version": dataset_version,
        "dataset_sha256": sha256_json(
            {
                "base_labels": base_labels_payload,
                "variants": variants_payload,
                "independent_cases": independent_payload,
            }
        ),
        "fixture_version": scenarios_payload["fixture_version"],
        "case_count": count,
        "source_counts": source_counts,
        "labeled_case_count": len(reciprocal_ranks),
        "abstention_case_count": abstention_cases,
        "metrics": {
            "overall_decision_accuracy": round(decisions_correct / count, 4) if count else 0.0,
            "labeled_top_1_accuracy": round(labeled_correct / len(reciprocal_ranks), 4)
            if reciprocal_ranks
            else 0.0,
            "mean_reciprocal_rank": round(sum(reciprocal_ranks) / len(reciprocal_ranks), 4)
            if reciprocal_ranks
            else 0.0,
            "mean_expected_support_evidence_recall": round(
                sum(evidence_recalls) / len(evidence_recalls), 4
            )
            if evidence_recalls
            else 0.0,
            "abstention_accuracy": round(correct_abstentions / abstention_cases, 4)
            if abstention_cases
            else 0.0,
        },
        "cases": outcomes,
    }
