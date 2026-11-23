from incident_atlas.evaluation import evaluate_expanded_dataset, evaluate_fixture_dataset


def test_base_evaluation_preserves_label_hash_and_improves_evidence_recall():
    result = evaluate_fixture_dataset()
    assert result["dataset_sha256"] == (
        "8dd1412c520acda5eb90d4e8f5b7ebd861e616967b1d0bc2897c19ccf142cdca"
    )
    assert result["metrics"]["top_1_accuracy"] == 1.0
    assert result["metrics"]["mean_expected_support_evidence_recall"] == 1.0


def test_expanded_dataset_has_positive_and_abstention_cases():
    result = evaluate_expanded_dataset()
    assert result["case_count"] == 12
    assert result["source_counts"] == {
        "authored_synthetic_base": 3,
        "authored_synthetic_independent": 3,
        "derived_synthetic_variant": 6,
    }
    assert result["labeled_case_count"] == 8
    assert result["abstention_case_count"] == 4
    assert result["metrics"]["labeled_top_1_accuracy"] == 1.0
    assert result["metrics"]["mean_expected_support_evidence_recall"] == 1.0
    assert result["metrics"]["abstention_accuracy"] == 1.0
    assert result["metrics"]["overall_decision_accuracy"] == 1.0


def test_independent_cases_are_not_derived_from_the_three_base_incidents():
    result = evaluate_expanded_dataset()
    independent = [
        case for case in result["cases"] if case["data_kind"] == "authored_synthetic_independent"
    ]
    assert {case["incident_id"] for case in independent} == {
        "eval-fraud-consumer-lag-001",
        "eval-checkout-cpu-throttling-002",
        "eval-shipping-span-ambiguous-003",
    }
    assert all(case["decision_correct"] for case in independent)
    assert all(case["expected_supporting_evidence_recall"] == 1 for case in independent[:2])

