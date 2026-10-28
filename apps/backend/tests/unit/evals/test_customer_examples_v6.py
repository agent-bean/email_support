from pathlib import Path

import pytest

from email_support.models.email_interpretation import FollowUpIntent
from evals.interpretation_review import load_rubric
from evals.models import CaseStatus, Relevance
from evals.runner import load_dataset

ROOT = Path(__file__).resolve().parents[3] / "evals" / "datasets"


@pytest.mark.parametrize("version", ["v6", "v7"])
def test_candidate_boundaries_and_preserved_inputs(version: str) -> None:
    old = load_dataset(ROOT / "customer-examples-v5")
    path = ROOT / f"customer-examples-{version}"
    dataset = load_dataset(path)
    rubric = load_rubric(path / "interpretation-rubric.json", dataset)
    cases = {case.id: case for case in dataset.cases}
    previous = {case.id: case for case in old.cases}
    pairs = {pair.id: pair for pair in rubric.pairs}
    assert all(case.status == CaseStatus.CANDIDATE for case in dataset.cases)
    assert not dataset.golden_reviews
    assert all(cases[id].email == case.email for id, case in previous.items())
    for language in ("en", "vi"):
        assert (
            cases[f"shopee-vietnam-{language}"].expected_relevance
            == Relevance.UNCERTAIN
        )
        assert (
            cases[f"ambiguous-next-step-{language}"].expected_relevance
            == Relevance.UNCERTAIN
        )
        assert (
            cases[f"explicit-reply-{language}"].expected_relevance
            == Relevance.UNCERTAIN
        )
        assert (
            cases[f"no-reply-needed-{language}"].expected_relevance
            == Relevance.IRRELEVANT
        )
    assert pairs["shopee-vietnam"].expected_follow_up == FollowUpIntent.REPLY
    assert pairs["ambiguous-next-step"].expected_follow_up == FollowUpIntent.UNCERTAIN
    assert pairs["explicit-reply"].expected_follow_up == FollowUpIntent.REPLY
    assert pairs["no-reply-needed"].expected_follow_up == FollowUpIntent.NONE


def test_v7_fpt_interest_has_reply_without_meeting_context() -> None:
    path = ROOT / "customer-examples-v7"
    dataset = load_dataset(path)
    rubric = load_rubric(path / "interpretation-rubric.json", dataset)
    for case in dataset.cases:
        if case.id.startswith("fpt-software-"):
            assert case.expected_relevance == Relevance.UNCERTAIN
    pair = next(pair for pair in rubric.pairs if pair.id == "fpt-software")
    assert pair.expected_follow_up == FollowUpIntent.REPLY


def test_v8_labels_all_follow_ups_without_changing_v7_cases() -> None:
    old = load_dataset(ROOT / "customer-examples-v7")
    path = ROOT / "customer-examples-v8"
    dataset = load_dataset(path)
    rubric = load_rubric(path / "interpretation-rubric.json", dataset)
    assert dataset.cases == old.cases
    assert all(pair.expected_follow_up is not None for pair in rubric.pairs)
    pairs = {pair.id: pair for pair in rubric.pairs}
    for name in ("vinamilk", "samsung-vietnam", "bosch-vietnam"):
        assert pairs[name].expected_follow_up == FollowUpIntent.REPLY
