from __future__ import annotations

import pytest

from email_support.workflows.company_briefing.state import merge_records


def test_merge_records_preserves_order_and_deduplicates_identical_ids() -> None:
    first = {"id": "one", "text": "first"}
    second = {"id": "two", "text": "second"}
    assert merge_records([first], [first, second]) == [first, second]


def test_merge_records_rejects_conflicting_ids() -> None:
    with pytest.raises(ValueError, match="conflicting"):
        merge_records(
            [{"id": "one", "text": "first"}], [{"id": "one", "text": "other"}]
        )
