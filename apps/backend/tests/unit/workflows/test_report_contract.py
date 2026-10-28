import pytest
from pydantic import ValidationError

from email_support.models.briefing import BriefingClaim, ClaimKind
from email_support.workflows.company_briefing.report import BriefingReport


def test_factual_claim_must_reference_available_evidence() -> None:
    with pytest.raises(ValidationError):
        BriefingReport(
            claims=[
                BriefingClaim(
                    id="1", kind=ClaimKind.FACT, text="Fact", evidence_ids=["missing"]
                )
            ],
            available_evidence_ids=["source"],
        )


def test_suggestions_are_distinct_and_do_not_need_evidence() -> None:
    result = BriefingReport(
        claims=[
            BriefingClaim(
                id="1", kind=ClaimKind.SUGGESTION, text="Ask about OCR", evidence_ids=[]
            )
        ],
        available_evidence_ids=[],
    )
    assert "Ask about OCR" in result.render()


def test_factual_claim_without_reference_fails() -> None:
    with pytest.raises(ValidationError):
        BriefingReport(
            claims=[
                BriefingClaim(id="1", kind=ClaimKind.NEED, text="Need", evidence_ids=[])
            ],
            available_evidence_ids=[],
        )


def test_model_text_cannot_insert_markdown_links_or_html() -> None:
    result = BriefingReport(
        claims=[
            BriefingClaim(
                id="1",
                kind=ClaimKind.SUGGESTION,
                text="[click](https://example.com) <script>bad</script>\n# heading",
                evidence_ids=[],
            )
        ],
        available_evidence_ids=[],
    )
    assert r"\[click\]" in result.render()
    assert r"\<script\>" in result.render()
    assert r"\# heading" in result.render()
