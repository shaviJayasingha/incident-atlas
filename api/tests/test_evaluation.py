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
    assert result["case_count"] == 9
    assert result["labeled_case_count"] == 6
    assert result["abstention_case_count"] == 3
    assert result["metrics"]["labeled_top_1_accuracy"] == 1.0
    assert result["metrics"]["mean_expected_support_evidence_recall"] == 1.0
    assert result["metrics"]["abstention_accuracy"] == 1.0
    assert result["metrics"]["overall_decision_accuracy"] == 1.0

