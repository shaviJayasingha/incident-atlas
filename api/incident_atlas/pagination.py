import base64
import json
from datetime import UTC, datetime

from incident_atlas.errors import ApiError


def encode_cursor(timestamp: datetime, record_id: str) -> str:
    payload = {"at": timestamp.astimezone(UTC).isoformat(), "id": record_id}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
    return encoded.decode().rstrip("=")


def decode_cursor(cursor: str | None) -> tuple[datetime, str] | None:
    if not cursor:
        return None
    try:
        padded = cursor + ("=" * (-len(cursor) % 4))
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        timestamp = datetime.fromisoformat(payload["at"])
        if timestamp.tzinfo is None or not isinstance(payload["id"], str):
            raise ValueError
        return timestamp.astimezone(UTC), payload["id"]
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise ApiError(400, "invalid_cursor", "The pagination cursor is invalid.") from None


def validate_window(start: datetime | None, end: datetime | None, max_minutes: int) -> None:
    if start and start.tzinfo is None or end and end.tzinfo is None:
        raise ApiError(400, "timezone_required", "Time filters must include a timezone.")
    if start and end and end <= start:
        raise ApiError(400, "invalid_time_range", "The end time must be later than the start time.")
    if start and end and (end - start).total_seconds() > max_minutes * 60:
        raise ApiError(
            400, "time_range_too_large", f"The time range cannot exceed {max_minutes} minutes."
        )
