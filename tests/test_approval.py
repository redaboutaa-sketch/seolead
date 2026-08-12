"""Approval state machine.

Two properties are being defended: approval cannot be reached without a human, and
a decision cannot be quietly reversed.
"""
from __future__ import annotations

import pytest

from app.core.enums import ApprovalState, ContentStatus
from app.services.approval_service import (InvalidTransition, assert_transition,
                                           can_transition, draft_status_for,
                                           is_publishable)


class TestTransitions:
    @pytest.mark.parametrize("target", [
        ApprovalState.APPROVED, ApprovalState.REJECTED, ApprovalState.NEEDS_REVISION,
    ])
    def test_pending_can_go_anywhere(self, target):
        assert can_transition(ApprovalState.PENDING, target)

    @pytest.mark.parametrize("target", [
        ApprovalState.APPROVED, ApprovalState.REJECTED, ApprovalState.NEEDS_REVISION,
    ])
    def test_needs_revision_can_be_resolved(self, target):
        assert can_transition(ApprovalState.NEEDS_REVISION, target)

    @pytest.mark.parametrize("terminal", [ApprovalState.APPROVED,
                                          ApprovalState.REJECTED])
    @pytest.mark.parametrize("target", list(ApprovalState))
    def test_terminal_states_are_final(self, terminal, target):
        assert not can_transition(terminal, target)

    def test_pending_to_pending_is_refused(self):
        """A no-op decision would create a decision record with no decision."""
        assert not can_transition(ApprovalState.PENDING, ApprovalState.PENDING)

    def test_assert_transition_raises_with_both_states(self):
        with pytest.raises(InvalidTransition) as exc:
            assert_transition(ApprovalState.APPROVED, ApprovalState.REJECTED)
        assert exc.value.current is ApprovalState.APPROVED
        assert exc.value.requested is ApprovalState.REJECTED


class TestPublishability:
    def test_only_approved_is_publishable(self):
        assert is_publishable(ApprovalState.APPROVED) is True
        for state in (ApprovalState.PENDING, ApprovalState.REJECTED,
                      ApprovalState.NEEDS_REVISION):
            assert is_publishable(state) is False

    def test_approval_module_does_not_depend_on_qa(self):
        """Structural guarantee: approval cannot be inferred from a QA result.

        The moment this module can see QA, 'QA passed, therefore approved' is one
        line away. Pinning the absent dependency is a blunt check, but it is the
        one that would actually fail if someone wired the two together.
        """
        import inspect

        from app.services import approval_service

        source = inspect.getsource(approval_service)
        assert "qa_service" not in source
        assert "QAStatus" not in source
        assert "qa_passed" not in source


class TestDraftStatusMapping:
    def test_each_state_maps_to_a_draft_status(self):
        assert draft_status_for(ApprovalState.PENDING) is ContentStatus.PENDING_APPROVAL
        assert draft_status_for(ApprovalState.APPROVED) is ContentStatus.APPROVED
        assert draft_status_for(ApprovalState.REJECTED) is ContentStatus.REJECTED
        assert draft_status_for(ApprovalState.NEEDS_REVISION) is \
            ContentStatus.NEEDS_REVISION
