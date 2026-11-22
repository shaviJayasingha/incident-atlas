import argparse
import json

from sqlalchemy import select

from incident_atlas.db import SessionLocal
from incident_atlas.evaluation import evaluate_expanded_dataset, evaluate_fixture_dataset
from incident_atlas.fixtures import fixture_manifest, seed_evaluation, seed_runtime
from incident_atlas.models import EvidenceSnapshot, Incident, SnapshotEvidence
from incident_atlas.rules import evaluate_rules


def baseline_results() -> list[dict[str, object]]:
    results = []
    with SessionLocal() as db:
        incidents = db.scalars(select(Incident).order_by(Incident.id)).all()
        for incident in incidents:
            snapshot = db.scalar(
                select(EvidenceSnapshot).where(
                    EvidenceSnapshot.incident_id == incident.id,
                    EvidenceSnapshot.id == f"snap-{incident.id}-{incident.fixture_version}",
                )
            )
            if snapshot is None:
                raise SystemExit(f"runtime fixture is not seeded: {incident.id}")
            rows = db.scalars(
                select(SnapshotEvidence)
                .where(
                    SnapshotEvidence.snapshot_id == snapshot.id,
                )
                .order_by(SnapshotEvidence.observed_at, SnapshotEvidence.evidence_id)
            ).all()
            evidence = [
                {
                    "evidence_id": row.evidence_id,
                    "kind": row.kind,
                    "observed_at": row.observed_at,
                    "payload": row.payload,
                }
                for row in rows
            ]
            results.append(
                {
                    "incident_id": incident.id,
                    "result": evaluate_rules(incident.id, incident.started_at, evidence),
                }
            )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(prog="incident-atlas")
    parser.add_argument(
        "command",
        choices=[
            "seed-runtime",
            "seed-evaluation",
            "fixture-manifest",
            "rules-baseline",
            "evaluate-fixtures",
            "evaluate-expanded",
        ],
    )
    args = parser.parse_args()
    if args.command == "evaluate-fixtures":
        print(json.dumps(evaluate_fixture_dataset(), indent=2, sort_keys=True))
        return
    if args.command == "evaluate-expanded":
        print(json.dumps(evaluate_expanded_dataset(), indent=2, sort_keys=True))
        return
    with SessionLocal() as db:
        if args.command == "seed-runtime":
            result = seed_runtime(db)
        elif args.command == "seed-evaluation":
            result = seed_evaluation(db)
        elif args.command == "fixture-manifest":
            result = fixture_manifest(db)
        else:
            result = baseline_results()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
