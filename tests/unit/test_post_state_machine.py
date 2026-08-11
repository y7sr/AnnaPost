"""Unit tests for the post state machine.

These tests verify the state transition rules defined in plan.annapost.md section 6.
They must pass before Phase 3 implementation begins, as they define the contract
that Phase 3 services will implement against.

The tests are organized by:
1. Valid transitions (should succeed)
2. Invalid transitions (should fail)
3. Helper function tests
4. Edge cases
"""

import pytest

from app.services.post_state_machine import (
    TRANSITION_TABLE,
    PostStatus,
    can_transition,
    get_allowed_transitions,
    is_terminal_status,
    validate_transition,
)


class TestValidTransitions:
    """Test all valid state transitions from section 6 of plan.annapost.md."""

    def test_draft_to_ready(self) -> None:
        """draft -> ready is valid."""
        assert can_transition(PostStatus.DRAFT, PostStatus.READY) is True
        assert validate_transition(PostStatus.DRAFT, PostStatus.READY) is True

    def test_draft_to_scheduled(self) -> None:
        """draft -> scheduled is valid."""
        assert can_transition(PostStatus.DRAFT, PostStatus.SCHEDULED) is True
        assert validate_transition(PostStatus.DRAFT, PostStatus.SCHEDULED) is True

    def test_draft_to_canceled(self) -> None:
        """draft -> canceled is valid."""
        assert can_transition(PostStatus.DRAFT, PostStatus.CANCELED) is True
        assert validate_transition(PostStatus.DRAFT, PostStatus.CANCELED) is True

    def test_ready_to_publishing(self) -> None:
        """ready -> publishing is valid."""
        assert can_transition(PostStatus.READY, PostStatus.PUBLISHING) is True
        assert validate_transition(PostStatus.READY, PostStatus.PUBLISHING) is True

    def test_scheduled_to_publishing(self) -> None:
        """scheduled -> publishing is valid."""
        assert can_transition(PostStatus.SCHEDULED, PostStatus.PUBLISHING) is True
        assert validate_transition(PostStatus.SCHEDULED, PostStatus.PUBLISHING) is True

    def test_publishing_to_published(self) -> None:
        """publishing -> published is valid."""
        assert can_transition(PostStatus.PUBLISHING, PostStatus.PUBLISHED) is True
        assert validate_transition(PostStatus.PUBLISHING, PostStatus.PUBLISHED) is True

    def test_publishing_to_failed(self) -> None:
        """publishing -> failed is valid."""
        assert can_transition(PostStatus.PUBLISHING, PostStatus.FAILED) is True
        assert validate_transition(PostStatus.PUBLISHING, PostStatus.FAILED) is True

    def test_failed_to_ready(self) -> None:
        """failed -> ready is valid (for retry)."""
        assert can_transition(PostStatus.FAILED, PostStatus.READY) is True
        assert validate_transition(PostStatus.FAILED, PostStatus.READY) is True

    def test_failed_to_publishing(self) -> None:
        """failed -> publishing is valid (immediate retry)."""
        assert can_transition(PostStatus.FAILED, PostStatus.PUBLISHING) is True
        assert validate_transition(PostStatus.FAILED, PostStatus.PUBLISHING) is True

    def test_failed_to_canceled(self) -> None:
        """failed -> canceled is valid (give up)."""
        assert can_transition(PostStatus.FAILED, PostStatus.CANCELED) is True
        assert validate_transition(PostStatus.FAILED, PostStatus.CANCELED) is True

    def test_published_to_delete_requested(self) -> None:
        """published -> delete_requested is valid."""
        assert can_transition(PostStatus.PUBLISHED, PostStatus.DELETE_REQUESTED) is True
        assert validate_transition(PostStatus.PUBLISHED, PostStatus.DELETE_REQUESTED) is True

    def test_delete_requested_to_deleted(self) -> None:
        """delete_requested -> deleted is valid."""
        assert can_transition(PostStatus.DELETE_REQUESTED, PostStatus.DELETED) is True
        assert validate_transition(PostStatus.DELETE_REQUESTED, PostStatus.DELETED) is True


class TestInvalidTransitions:
    """Test that invalid transitions are correctly rejected."""

    def test_published_to_draft(self) -> None:
        """published -> draft is NOT valid (can't go back)."""
        assert can_transition(PostStatus.PUBLISHED, PostStatus.DRAFT) is False
        assert validate_transition(PostStatus.PUBLISHED, PostStatus.DRAFT) is False

    def test_published_to_ready(self) -> None:
        """published -> ready is NOT valid."""
        assert can_transition(PostStatus.PUBLISHED, PostStatus.READY) is False

    def test_published_to_scheduled(self) -> None:
        """published -> scheduled is NOT valid."""
        assert can_transition(PostStatus.PUBLISHED, PostStatus.SCHEDULED) is False

    def test_published_to_publishing(self) -> None:
        """published -> publishing is NOT valid (already published)."""
        assert can_transition(PostStatus.PUBLISHED, PostStatus.PUBLISHING) is False

    def test_published_to_failed(self) -> None:
        """published -> failed is NOT valid."""
        assert can_transition(PostStatus.PUBLISHED, PostStatus.FAILED) is False

    def test_published_to_deleted(self) -> None:
        """published -> deleted is NOT valid (must go through delete_requested)."""
        assert can_transition(PostStatus.PUBLISHED, PostStatus.DELETED) is False

    def test_publishing_to_ready(self) -> None:
        """publishing -> ready is NOT valid (can't go back mid-publish)."""
        assert can_transition(PostStatus.PUBLISHING, PostStatus.READY) is False

    def test_publishing_to_scheduled(self) -> None:
        """publishing -> scheduled is NOT valid."""
        assert can_transition(PostStatus.PUBLISHING, PostStatus.SCHEDULED) is False

    def test_publishing_to_draft(self) -> None:
        """publishing -> draft is NOT valid."""
        assert can_transition(PostStatus.PUBLISHING, PostStatus.DRAFT) is False

    def test_ready_to_draft(self) -> None:
        """ready -> draft is NOT valid."""
        assert can_transition(PostStatus.READY, PostStatus.DRAFT) is False

    def test_ready_to_scheduled(self) -> None:
        """ready -> scheduled is NOT valid (use scheduled directly from draft)."""
        assert can_transition(PostStatus.READY, PostStatus.SCHEDULED) is False

    def test_ready_to_published(self) -> None:
        """ready -> published is NOT valid (must go through publishing)."""
        assert can_transition(PostStatus.READY, PostStatus.PUBLISHED) is False

    def test_scheduled_to_ready(self) -> None:
        """scheduled -> ready is NOT valid."""
        assert can_transition(PostStatus.SCHEDULED, PostStatus.READY) is False

    def test_scheduled_to_draft(self) -> None:
        """scheduled -> draft is NOT valid."""
        assert can_transition(PostStatus.SCHEDULED, PostStatus.DRAFT) is False

    def test_failed_to_published(self) -> None:
        """failed -> published is NOT valid (must go through publishing)."""
        assert can_transition(PostStatus.FAILED, PostStatus.PUBLISHED) is False

    def test_failed_to_scheduled(self) -> None:
        """failed -> scheduled is NOT valid."""
        assert can_transition(PostStatus.FAILED, PostStatus.SCHEDULED) is False

    def test_delete_requested_to_published(self) -> None:
        """delete_requested -> published is NOT valid."""
        assert can_transition(PostStatus.DELETE_REQUESTED, PostStatus.PUBLISHED) is False

    def test_delete_requested_to_ready(self) -> None:
        """delete_requested -> ready is NOT valid."""
        assert can_transition(PostStatus.DELETE_REQUESTED, PostStatus.READY) is False

    def test_deleted_to_any(self) -> None:
        """deleted is terminal - no transitions allowed."""
        for status in PostStatus:
            if status == PostStatus.DELETED:
                continue
            assert can_transition(PostStatus.DELETED, status) is False, (
                f"deleted -> {status.value} should not be allowed"
            )

    def test_canceled_to_any(self) -> None:
        """canceled is terminal - no transitions allowed."""
        for status in PostStatus:
            if status == PostStatus.CANCELED:
                continue
            assert can_transition(PostStatus.CANCELED, status) is False, (
                f"canceled -> {status.value} should not be allowed"
            )


class TestValidateTransitionWithException:
    """Test validate_transition with raise_on_invalid=True."""

    def test_valid_transition_no_exception(self) -> None:
        """Valid transitions should not raise even with raise_on_invalid=True."""
        # Should not raise
        result = validate_transition(PostStatus.DRAFT, PostStatus.READY, raise_on_invalid=True)
        assert result is True

    def test_invalid_transition_raises(self) -> None:
        """Invalid transitions should raise ValueError with raise_on_invalid=True."""
        with pytest.raises(ValueError) as exc_info:
            validate_transition(PostStatus.PUBLISHED, PostStatus.DRAFT, raise_on_invalid=True)

        assert "Invalid transition" in str(exc_info.value)
        assert "published -> draft" in str(exc_info.value)

    def test_raises_with_allowed_alternatives(self) -> None:
        """Error message should include allowed transitions."""
        with pytest.raises(ValueError) as exc_info:
            validate_transition(PostStatus.READY, PostStatus.PUBLISHED, raise_on_invalid=True)

        error_msg = str(exc_info.value)
        assert "published" not in error_msg.split("Allowed transitions")[1].split("[")[0]
        assert "publishing" in error_msg


class TestGetAllowedTransitions:
    """Test the get_allowed_transitions helper function."""

    def test_draft_allowed(self) -> None:
        """Draft can go to ready, scheduled, canceled."""
        allowed = get_allowed_transitions(PostStatus.DRAFT)
        assert allowed == frozenset(
            {
                PostStatus.READY,
                PostStatus.SCHEDULED,
                PostStatus.CANCELED,
            }
        )

    def test_ready_allowed(self) -> None:
        """Ready can only go to publishing."""
        allowed = get_allowed_transitions(PostStatus.READY)
        assert allowed == frozenset({PostStatus.PUBLISHING})

    def test_scheduled_allowed(self) -> None:
        """Scheduled can only go to publishing."""
        allowed = get_allowed_transitions(PostStatus.SCHEDULED)
        assert allowed == frozenset({PostStatus.PUBLISHING})

    def test_publishing_allowed(self) -> None:
        """Publishing can go to published or failed."""
        allowed = get_allowed_transitions(PostStatus.PUBLISHING)
        assert allowed == frozenset(
            {
                PostStatus.PUBLISHED,
                PostStatus.FAILED,
            }
        )

    def test_failed_allowed(self) -> None:
        """Failed can go to ready, publishing, or canceled."""
        allowed = get_allowed_transitions(PostStatus.FAILED)
        assert allowed == frozenset(
            {
                PostStatus.READY,
                PostStatus.PUBLISHING,
                PostStatus.CANCELED,
            }
        )

    def test_published_allowed(self) -> None:
        """Published can only go to delete_requested."""
        allowed = get_allowed_transitions(PostStatus.PUBLISHED)
        assert allowed == frozenset({PostStatus.DELETE_REQUESTED})

    def test_delete_requested_allowed(self) -> None:
        """Delete requested can only go to deleted."""
        allowed = get_allowed_transitions(PostStatus.DELETE_REQUESTED)
        assert allowed == frozenset({PostStatus.DELETED})

    def test_deleted_allowed_empty(self) -> None:
        """Deleted has no allowed transitions (terminal)."""
        allowed = get_allowed_transitions(PostStatus.DELETED)
        assert allowed == frozenset()

    def test_canceled_allowed_empty(self) -> None:
        """Canceled has no allowed transitions (terminal)."""
        allowed = get_allowed_transitions(PostStatus.CANCELED)
        assert allowed == frozenset()


class TestIsTerminalStatus:
    """Test the is_terminal_status helper function."""

    def test_deleted_is_terminal(self) -> None:
        """Deleted is a terminal status."""
        assert is_terminal_status(PostStatus.DELETED) is True

    def test_canceled_is_terminal(self) -> None:
        """Canceled is a terminal status."""
        assert is_terminal_status(PostStatus.CANCELED) is True

    def test_draft_not_terminal(self) -> None:
        """Draft is not a terminal status."""
        assert is_terminal_status(PostStatus.DRAFT) is False

    def test_ready_not_terminal(self) -> None:
        """Ready is not a terminal status."""
        assert is_terminal_status(PostStatus.READY) is False

    def test_scheduled_not_terminal(self) -> None:
        """Scheduled is not a terminal status."""
        assert is_terminal_status(PostStatus.SCHEDULED) is False

    def test_publishing_not_terminal(self) -> None:
        """Publishing is not a terminal status."""
        assert is_terminal_status(PostStatus.PUBLISHING) is False

    def test_published_not_terminal(self) -> None:
        """Published is not a terminal status."""
        assert is_terminal_status(PostStatus.PUBLISHED) is False

    def test_failed_not_terminal(self) -> None:
        """Failed is not a terminal status."""
        assert is_terminal_status(PostStatus.FAILED) is False

    def test_delete_requested_not_terminal(self) -> None:
        """Delete requested is not a terminal status."""
        assert is_terminal_status(PostStatus.DELETE_REQUESTED) is False


class TestTransitionTableStructure:
    """Test the structure of the TRANSITION_TABLE itself."""

    def test_all_statuses_in_table(self) -> None:
        """Every PostStatus should have an entry in TRANSITION_TABLE."""
        for status in PostStatus:
            assert status in TRANSITION_TABLE, f"{status.value} missing from TRANSITION_TABLE"

    def test_table_matches_spec(self) -> None:
        """Verify the table matches the spec from plan.annapost.md section 6."""
        # This is a comprehensive check that the table matches the documented transitions
        expected = {
            PostStatus.DRAFT: {PostStatus.READY, PostStatus.SCHEDULED, PostStatus.CANCELED},
            PostStatus.READY: {PostStatus.PUBLISHING},
            PostStatus.SCHEDULED: {PostStatus.PUBLISHING},
            PostStatus.PUBLISHING: {PostStatus.PUBLISHED, PostStatus.FAILED},
            PostStatus.FAILED: {PostStatus.READY, PostStatus.PUBLISHING, PostStatus.CANCELED},
            PostStatus.PUBLISHED: {PostStatus.DELETE_REQUESTED},
            PostStatus.DELETE_REQUESTED: {PostStatus.DELETED},
            PostStatus.DELETED: set(),
            PostStatus.CANCELED: set(),
        }

        for status, expected_targets in expected.items():
            actual_targets = TRANSITION_TABLE[status]
            assert actual_targets == frozenset(expected_targets), (
                f"TRANSITION_TABLE[{status.value}] = {actual_targets}, "
                f"expected {frozenset(expected_targets)}"
            )


class TestSameStatusTransition:
    """Test transitions to the same status (should generally be invalid)."""

    def test_same_status_invalid(self) -> None:
        """Transitioning to the same status should be invalid (except potentially for idempotent operations)."""
        # Based on the spec, same-status transitions are not listed as valid
        # So they should all be invalid
        for status in PostStatus:
            assert can_transition(status, status) is False, (
                f"{status.value} -> {status.value} should be invalid"
            )
