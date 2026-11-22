from datetime import datetime

from incident_atlas.evaluation import evaluate_fixture_dataset
from incident_atlas.fixtures import (
    LABELS_PATH,
    SCENARIOS_PATH,
    build_evidence_items,
    load_json,
    parse_dt,
)
from incident_atlas.rules import evaluate_rules


def test_rules_baseline_is_deterministic_and_scores_all_base_cases():
    first = evaluate_fixture_dataset()
    second = evaluate_fixture_dataset()

    assert first == second
    assert first["case_count"] == 3
    assert first["metrics"]["top_1_accuracy"] == 1.0
    assert first["metrics"]["abstention_rate"] == 0.0
    assert all(case["top_1_correct"] for case in first["cases"])


def test_rules_references_are_fixture_evidence_ids():
    scenarios = load_json(SCENARIOS_PATH)["scenarios"]
    for scenario in scenarios:
        items = build_evidence_items(scenario)
        start = datetime.fromisoformat(scenario["started_at"].replace("Z", "+00:00"))
        report = evaluate_rules(scenario["id"], start, items)
        available = {item["evidence_id"] for item in items}
        references = {
            evidence_id for rule in report["fired_rules"] for evidence_id in rule["evidence_ids"]
        }
        assert references <= available


def test_public_rules_signals_do_not_reuse_hidden_evaluation_labels():
    scenarios = load_json(SCENARIOS_PATH)["scenarios"]
    labels = load_json(LABELS_PATH)["cases"]
    expected_labels = {case["expected_primary_label"] for case in labels}
    public_signals = []
    for scenario in scenarios:
        public_signals.extend(
            evaluate_rules(
                scenario["id"],
                parse_dt(scenario["started_at"]),
                build_evidence_items(scenario),
            )["ranked_labels"]
        )
    assert expected_labels.isdisjoint(public_signals)
