"""Normalize volatile Graph API insight names into stable local metrics.

This is the sole module allowed to mention Graph API insight metric names.
The rest of the application works only with ``NormalizedPostMetrics`` and
persists the untouched raw payload alongside each snapshot.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field


class NormalizedPostMetrics(BaseModel):
    """Stable metric fields where ``None`` means unavailable, never zero."""

    views: int | None = None
    reach: int | None = None
    plays: int | None = None
    avg_watch_time_ms: int | None = None
    total_watch_time_ms: int | None = None
    likes: int | None = None
    comments: int | None = None
    saved: int | None = None
    shares: int | None = None
    total_interactions: int | None = None
    profile_activity: int | None = None
    follows: int | None = None
    raw_metrics_json: dict[str, Any] = Field(default_factory=dict)


# Graph API names belong here, not in services, models, repositories, or
# runners. Multiple upstream names may intentionally feed one stable field.
GRAPH_METRIC_TO_FIELD = {
    "impressions": "views",
    "video_views": "views",
    "reach": "reach",
    "plays": "plays",
    "avg_watch_time": "avg_watch_time_ms",
    "total_watch_time": "total_watch_time_ms",
    "likes": "likes",
    "comments": "comments",
    "saved": "saved",
    "shares": "shares",
    "total_interactions": "total_interactions",
    "profile_activity": "profile_activity",
    "follows_and_unfollows": "follows",
}


def _integer_value(record: Mapping[str, Any]) -> int | None:
    """Extract one explicit integer value without turning missing data into 0."""
    value = record.get("value")
    if value is None:
        values = record.get("values")
        if isinstance(values, list) and values:
            latest = values[-1]
            if isinstance(latest, Mapping):
                value = latest.get("value")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def normalize_post_metrics(raw_payload: Mapping[str, Any]) -> NormalizedPostMetrics:
    """Normalize a Graph insight response while preserving the raw payload.

    Unknown, malformed, and unavailable metrics remain ``None``. An explicit
    zero survives unchanged, which preserves the distinction between zero and
    unavailable required by the database contract.
    """
    values: dict[str, int | None] = {}
    raw_data = raw_payload.get("data")
    if isinstance(raw_data, list):
        for record in raw_data:
            if not isinstance(record, Mapping):
                continue
            name = record.get("name")
            if not isinstance(name, str):
                continue
            target = GRAPH_METRIC_TO_FIELD.get(name)
            if target is not None:
                values[target] = _integer_value(record)

    return NormalizedPostMetrics(
        **values,
        raw_metrics_json=dict(raw_payload),
    )
