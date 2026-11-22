import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from threading import Lock

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from incident_atlas.config import Settings
from incident_atlas.errors import ApiError
from incident_atlas.models import GuestRateEvent

_LIVE_LOCK = Lock()
_LIVE_INFLIGHT = 0


def source_hash(settings: Settings, source: str | None) -> str:
    normalized = source or "unknown"
    key = settings.rate_limit_hmac_key.get_secret_value().encode()
    return hmac.new(key, normalized.encode(), hashlib.sha256).hexdigest()


def idempotency_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def enforce_rate_limit(
    db: Session,
    settings: Settings,
    source: str | None,
    action: str,
) -> str:
    subject = source_hash(settings, source)
    if not settings.rate_limit_enabled:
        return subject

    if action == "live":
        maximum = settings.rate_live_runs
        window = settings.rate_live_window_seconds
    else:
        maximum = settings.rate_approvals
        window = settings.rate_approval_window_seconds
    cutoff = datetime.now(UTC) - timedelta(seconds=window)
    retention_cutoff = datetime.now(UTC) - timedelta(
        seconds=max(settings.rate_live_window_seconds, settings.rate_approval_window_seconds)
    )
    db.execute(delete(GuestRateEvent).where(GuestRateEvent.occurred_at < retention_cutoff))
    db.commit()

    # Serialize a source/action pair across API workers without retaining a raw IP address.
    advisory_key = f"{subject}:{action}"
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": advisory_key}
    )
    count = (
        db.scalar(
            select(func.count())
            .select_from(GuestRateEvent)
            .where(
                GuestRateEvent.subject_hash == subject,
                GuestRateEvent.action == action,
                GuestRateEvent.occurred_at >= cutoff,
            )
        )
        or 0
    )
    if count >= maximum:
        db.rollback()
        raise ApiError(
            429,
            "rate_limited",
            "The public demo limit was reached; try again later.",
            retryable=True,
        )

    db.add(GuestRateEvent(subject_hash=subject, action=action))
    db.commit()
    return subject


def acquire_live_slot(maximum: int) -> None:
    global _LIVE_INFLIGHT
    with _LIVE_LOCK:
        if _LIVE_INFLIGHT >= maximum:
            raise ApiError(
                429,
                "live_capacity_reached",
                "All live investigation slots are busy; use a replay or retry shortly.",
                retryable=True,
            )
        _LIVE_INFLIGHT += 1


def release_live_slot() -> None:
    global _LIVE_INFLIGHT
    with _LIVE_LOCK:
        _LIVE_INFLIGHT = max(0, _LIVE_INFLIGHT - 1)


def retry_after_seconds(window: int) -> int:
    return max(1, int(window))
