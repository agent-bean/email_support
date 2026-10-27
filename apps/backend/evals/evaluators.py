"""Deterministic reference checks and explicitly human-owned semantic review."""

from __future__ import annotations

from email_support.models.briefing import BriefingClaim, ClaimKind
from evals.models import (
    ClaimEvaluation,
    ClaimIntegrity,
    ClaimSupport,
    ReviewLabel,
)


def evaluate_claim(
    claim: BriefingClaim,
    source_ids: set[str],
    review: ReviewLabel | None,
    expected_claim_ids: set[str] | None = None,
) -> ClaimEvaluation:
    """Check identifiers without inferring semantic support from source presence."""

    if expected_claim_ids is not None and (
        (claim.kind is ClaimKind.FACT and claim.id not in expected_claim_ids)
        or (claim.kind is not ClaimKind.FACT and claim.id in expected_claim_ids)
    ):
        integrity = ClaimIntegrity.MISSING_CLAIM
    elif not set(claim.evidence_ids).issubset(source_ids):
        integrity = ClaimIntegrity.MISSING_SOURCE
    else:
        integrity = ClaimIntegrity.VALID

    if claim.kind is not ClaimKind.FACT:
        support = ClaimSupport.NOT_APPLICABLE
    elif integrity is not ClaimIntegrity.VALID:
        support = ClaimSupport.NOT_ASSESSED
    elif review is None:
        support = ClaimSupport.PENDING_HUMAN_REVIEW
    elif review is ReviewLabel.SUPPORTED:
        support = ClaimSupport.SUPPORTED
    else:
        support = ClaimSupport.UNSUPPORTED

    return ClaimEvaluation(claim_id=claim.id, integrity=integrity, support=support)
