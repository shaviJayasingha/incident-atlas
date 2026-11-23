import hashlib
import hmac
import ipaddress
from datetime import UTC, datetime, timedelta
from threading import Lock

from sqlalchemy import func, select, text
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


def trusted_client_address(
    peer_address: str | None,
    forwarded_for: str | None,
    trusted_proxy_cidrs: list[str],
) -> str | None:
    """Use X-Forwarded-For only when the direct peer is explicitly trusted.

    When the proxy chain includes a client-supplied prefix, walk from the trusted
    socket peer toward the client and select the nearest untrusted hop.
    """
    if not peer_address:
        return None
    try:
        peer = ipaddress.ip_address(peer_address)
    except ValueError:
        return peer_address

    networks = [ipaddress.ip_network(item, strict=False) for item in trusted_proxy_cidrs]
    if not any(peer in network for network in networks) or not forwarded_for:
        return peer.compressed

    try:
        chain = [ipaddress.ip_address(item.strip()) for item in forwarded_for.split(",")]
    except ValueError:
        return peer.compressed

    for candidate in reversed(chain):
        if not any(candidate in network for network in networks):
            return candidate.compressed
    return peer.compressed


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
    # Runtime credentials cannot delete arbitrary rows. The fixed SECURITY DEFINER
    # function only removes events older than the maximum supported rate window.
    db.execute(text("SELECT public.prune_expired_guest_rate_events()"))
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


def reserve_global_live_budget(db: Session, settings: Settings) -> None:
    """Atomically reserve one shared model-call slot across visitors and API workers."""
    global_subject = source_hash(settings, "incident-atlas-global-live-budget-v1")
    global_cutoff = datetime.now(UTC) - timedelta(seconds=settings.rate_live_global_window_seconds)
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"{global_subject}:live_global"},
    )
    global_count = (
        db.scalar(
            select(func.count())
            .select_from(GuestRateEvent)
            .where(
                GuestRateEvent.subject_hash == global_subject,
                GuestRateEvent.action == "live_global",
                GuestRateEvent.occurred_at >= global_cutoff,
            )
        )
        or 0
    )
    if global_count >= settings.rate_live_global_runs:
        db.rollback()
        raise ApiError(
            429,
            "live_global_limit_reached",
            "The shared live-investigation budget is exhausted for this time window.",
            retryable=True,
        )
    db.add(GuestRateEvent(subject_hash=global_subject, action="live_global"))
    db.commit()


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
