"""The human approval gate.

Two invariants, both enforced here rather than by convention:

1. **Approval is never inferred.** Nothing in this module reads a QA result. A
   draft whose QA passed is `PENDING`, exactly like one whose QA failed. The only
   way to reach `APPROVED` is for a person to say so, and the actor is recorded.

2. **A decision is not silently reversible.** `APPROVED` and `REJECTED` are
   terminal. Reopening means `NEEDS_REVISION`, which is a decision an operator
   takes deliberately and which leaves the previous state in the audit trail.
"""
from __future__ import annotations

from app.core.enums import ApprovalState, ContentStatus

# Which transitions are legal. Absent pair → refused.
_ALLOWED: dict[ApprovalState, frozenset[ApprovalState]] = {
    ApprovalState.PENDING: frozenset({
        ApprovalState.APPROVED, ApprovalState.REJECTED, ApprovalState.NEEDS_REVISION,
    }),
    # A revision request can be resolved either way, or re-requested.
    ApprovalState.NEEDS_REVISION: frozenset({
        ApprovalState.APPROVED, ApprovalState.REJECTED, ApprovalState.NEEDS_REVISION,
    }),
    ApprovalState.APPROVED: frozenset(),
    ApprovalState.REJECTED: frozenset(),
}

_DRAFT_STATUS_FOR: dict[ApprovalState, ContentStatus] = {
    ApprovalState.PENDING: ContentStatus.PENDING_APPROVAL,
    ApprovalState.APPROVED: ContentStatus.APPROVED,
    ApprovalState.REJECTED: ContentStatus.REJECTED,
    ApprovalState.NEEDS_REVISION: ContentStatus.NEEDS_REVISION,
}


class InvalidTransition(Exception):
    def __init__(self, current: ApprovalState, requested: ApprovalState):
        self.current = current
        self.requested = requested
        super().__init__(
            f"cannot move approval from {current.value} to {requested.value}"
        )


def can_transition(current: ApprovalState, requested: ApprovalState) -> bool:
    return requested in _ALLOWED.get(current, frozenset())


def assert_transition(current: ApprovalState, requested: ApprovalState) -> None:
    if not can_transition(current, requested):
        raise InvalidTransition(current, requested)


def draft_status_for(state: ApprovalState) -> ContentStatus:
    return _DRAFT_STATUS_FOR[state]


def is_publishable(state: ApprovalState) -> bool:
    """The only place that answers 'may this leave the factory?'.

    Phase 2 publishes nothing, but the predicate exists now so that Phase 5 has
    one function to call rather than a boolean check copied into three services.
    """
    return state is ApprovalState.APPROVED
