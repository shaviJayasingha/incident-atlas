import pytest

from incident_atlas.errors import ApiError, ProviderInvalidOutput
from incident_atlas.provider import DraftHypothesis, InvestigationDraft
from incident_atlas.service import _failure_response, _validate_evidence_references


def _draft(evidence_ids: list[str]) -> InvestigationDraft:
    return InvestigationDraft(
        uncertainty="The synthetic evidence is incomplete.",
        hypotheses=[
            DraftHypothesis(
                rank=1,
                statement="A dependency may be slow.",
                confidence="low",
                confidence_note="Only one fixture signal is available.",
                supporting_evidence_ids=evidence_ids,
                contradicting_evidence_ids=[],
                next_read_only_check="Compare adjacent trace spans.",
                mitigation_summary="Simulate a traffic shift.",
            )
        ],
    )


def test_valid_hypothesis_citation_must_resolve_in_snapshot():
    _validate_evidence_references(_draft(["ev-known"]), {"ev-known"})

    with pytest.raises(ProviderInvalidOutput, match="outside the investigation snapshot"):
        _validate_evidence_references(_draft(["ev-unknown"]), {"ev-known"})


def test_hypothesis_must_cite_evidence_and_cannot_duplicate_citations():
    with pytest.raises(ProviderInvalidOutput, match="at least one evidence item"):
        _validate_evidence_references(_draft([]), {"ev-known"})

    duplicated = _draft(["ev-known"])
    duplicated.hypotheses[0].contradicting_evidence_ids = ["ev-known"]
    with pytest.raises(ProviderInvalidOutput, match="duplicate evidence references"):
        _validate_evidence_references(duplicated, {"ev-known"})


@pytest.mark.parametrize(
    ("status", "http_status", "code"),
    [
        ("timed_out", 504, "investigation_timeout"),
        ("refused", 422, "provider_refused"),
        ("invalid_output", 502, "invalid_model_output"),
        ("failed", 503, "provider_unavailable"),
    ],
)
def test_live_error_status_mapping(status, http_status, code):
    error = _failure_response(status, "provider_unavailable")
    assert isinstance(error, ApiError)
    assert error.status == http_status
    assert error.code == code
