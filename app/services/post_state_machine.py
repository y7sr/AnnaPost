"""Post state machine for Instagram posts.

This module encodes the state transition rules defined in plan.annapost.md section 6.
It provides a centralized, explicit structure for validating post status transitions,
ensuring that arbitrary state changes are not allowed.

The state machine is the source of truth for what transitions are valid.
Phase 3 services must use this module rather than implementing transition logic ad-hoc.
"""

from __future__ import annotations

from app.db.models.post import PostStatus

# Transition table: maps each status to the set of statuses it can transition TO.
# This is the explicit encoding of the transition rules from plan.annapost.md section 6.
#
# Valid transitions:
#   draft -> ready, scheduled, canceled
#   ready -> publishing
#   scheduled -> publishing
#   publishing -> published, failed
#   failed -> ready, publishing, canceled
#   published -> delete_requested
#   delete_requested -> deleted
#
# Note: Once in 'deleted' or 'canceled' states, no further transitions are allowed
# (these are terminal states).
TRANSITION_TABLE: dict[PostStatus, frozenset[PostStatus]] = {
    PostStatus.DRAFT: frozenset(
        {
            PostStatus.READY,
            PostStatus.SCHEDULED,
            PostStatus.CANCELED,
        }
    ),
    PostStatus.READY: frozenset({PostStatus.PUBLISHING}),
    PostStatus.SCHEDULED: frozenset({PostStatus.PUBLISHING}),
    PostStatus.PUBLISHING: frozenset(
        {
            PostStatus.PUBLISHED,
            PostStatus.FAILED,
        }
    ),
    PostStatus.FAILED: frozenset(
        {
            PostStatus.READY,
            PostStatus.PUBLISHING,
            PostStatus.CANCELED,
        }
    ),
    PostStatus.PUBLISHED: frozenset({PostStatus.DELETE_REQUESTED}),
    PostStatus.DELETE_REQUESTED: frozenset({PostStatus.DELETED}),
    PostStatus.DELETED: frozenset(),  # Terminal state - no outgoing transitions
    PostStatus.CANCELED: frozenset(),  # Terminal state - no outgoing transitions
}


def can_transition(from_status: PostStatus, to_status: PostStatus) -> bool:
    """Check if a transition from one status to another is valid.

    Args:
        from_status: The current status of the post.
        to_status: The target status to transition to.

    Returns:
        True if the transition is allowed, False otherwise.

    Example:
        >>> can_transition(PostStatus.DRAFT, PostStatus.READY)
        True
        >>> can_transition(PostStatus.PUBLISHED, PostStatus.DRAFT)
        False
    """
    if from_status not in TRANSITION_TABLE:
        # Unknown status - treat as invalid
        return False

    allowed_targets = TRANSITION_TABLE[from_status]
    return to_status in allowed_targets


def validate_transition(
    from_status: PostStatus,
    to_status: PostStatus,
    raise_on_invalid: bool = False,
) -> bool:
    """Validate a state transition, optionally raising an exception on invalid transitions.

    This is the primary entry point for state transition validation.
    Services should call this function before attempting to change a post's status.

    Args:
        from_status: The current status of the post.
        to_status: The target status to transition to.
        raise_on_invalid: If True, raise ValueError on invalid transition.
                        If False (default), return False for invalid transitions.

    Returns:
        True if the transition is valid, False otherwise.

    Raises:
        ValueError: If raise_on_invalid is True and the transition is invalid.

    Example:
        >>> validate_transition(PostStatus.READY, PostStatus.PUBLISHING)
        True
        >>> validate_transition(PostStatus.PUBLISHED, PostStatus.DRAFT)
        False
        >>> validate_transition(PostStatus.PUBLISHED, PostStatus.DRAFT, raise_on_invalid=True)
        ValueError: Invalid transition: published -> draft
    """
    is_valid = can_transition(from_status, to_status)

    if not is_valid and raise_on_invalid:
        raise ValueError(
            f"Invalid transition: {from_status.value} -> {to_status.value}. "
            f"Allowed transitions from {from_status.value}: "
            f"{sorted(t.value for t in TRANSITION_TABLE[from_status])}"
        )

    return is_valid


def get_allowed_transitions(from_status: PostStatus) -> frozenset[PostStatus]:
    """Get the set of allowed target statuses for a given current status.

    Args:
        from_status: The current status of the post.

    Returns:
        A frozen set of PostStatus values that can be transitioned to.
        Returns an empty set if the status is terminal (deleted, canceled).

    Example:
        >>> get_allowed_transitions(PostStatus.DRAFT)
        {<PostStatus.READY: 'ready'>, <PostStatus.SCHEDULED: 'scheduled'>, <PostStatus.CANCELED: 'canceled'>}
        >>> get_allowed_transitions(PostStatus.DELETED)
        set()
    """
    return TRANSITION_TABLE.get(from_status, frozenset())


def is_terminal_status(status: PostStatus) -> bool:
    """Check if a status is terminal (no outgoing transitions allowed).

    Args:
        status: The status to check.

    Returns:
        True if the status is terminal (deleted or canceled), False otherwise.

    Example:
        >>> is_terminal_status(PostStatus.DELETED)
        True
        >>> is_terminal_status(PostStatus.PUBLISHED)
        False
    """
    return len(TRANSITION_TABLE.get(status, set())) == 0
