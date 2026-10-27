from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from evals.interpretation_review import build_review, load_rubric, main
from evals.runner import EvaluationInputError, load_dataset
from scripts.evaluate_interpretation import select_cases

ROOT = Path(__file__).parents[3] / "evals" / "datasets" / "customer-examples-v1"


def test_rubric_binds_every_bilingual_pair_to_exact_dataset() -> None:
    dataset = load_dataset(ROOT)
    rubric = load_rubric(ROOT / "interpretation-rubric.json", dataset)
    assert len(rubric.pairs) == 6
    assert all(set(pair.cases) == {"en", "vi"} for pair in rubric.pairs)


def test_retry_selects_requested_cases_without_changing_dataset_binding() -> None:
    dataset = load_dataset(ROOT)
    selected = select_cases(dataset, [dataset.cases[1].id])
    assert [case.id for case in selected] == [dataset.cases[1].id]
    assert len(select_cases(dataset, [])) == len(dataset.cases)
    with pytest.raises(ValueError):
        select_cases(dataset, ["unknown"])


def test_rubric_rejects_changed_case_hash(tmp_path: Path) -> None:
    dataset = load_dataset(ROOT)
    raw = json.loads((ROOT / "interpretation-rubric.json").read_text())
    raw["pairs"][0]["cases"]["en"]["case_hash"] = "0" * 64
    path = tmp_path / "rubric.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(EvaluationInputError):
        load_rubric(path, dataset)


def test_missing_results_are_not_scored_as_negative_and_pairs_are_pending() -> None:
    dataset = load_dataset(ROOT)
    rubric = load_rubric(ROOT / "interpretation-rubric.json", dataset)
    report = build_review(dataset, rubric, [])
    assert len(report["cases"]) == 12
    assert all(item["status"] == "missing" for item in report["cases"])
    assert all(
        item["review_status"] == "pending_human_review" for item in report["pairs"]
    )
    assert all(item["relevance_equal"] is None for item in report["pairs"])


def test_duplicate_or_unknown_case_results_are_rejected() -> None:
    dataset = load_dataset(ROOT)
    rubric = load_rubric(ROOT / "interpretation-rubric.json", dataset)
    with pytest.raises(EvaluationInputError):
        build_review(dataset, rubric, [{"case_id": "unknown", "status": "error"}])
    with pytest.raises(EvaluationInputError):
        build_review(
            dataset, rubric, [{"case_id": dataset.cases[0].id, "status": "error"}] * 2
        )


def test_valid_capture_requires_bound_input_and_validated_output() -> None:
    dataset = load_dataset(ROOT)
    rubric = load_rubric(ROOT / "interpretation-rubric.json", dataset)
    case = dataset.cases[0]
    record: dict[str, Any] = {
        "case_id": case.id,
        "status": "valid",
        "input": {
            "origin_kind": "evaluation",
            "origin_key": case.id,
            "payload": {
                "sender_email": case.email.from_address,
                "sender_display_name": None,
                "subject": case.email.subject,
                "body": case.email.body,
                "received_at": case.clock.isoformat(),
                "meeting_state": "absent",
                "meeting": None,
            },
        },
        "output": {
            "relevance": "relevant",
            "company_candidates": [],
            "contact_candidates": [],
            "stated_needs": [],
            "ambiguity_reasons": [],
            "unknowns": [],
        },
    }
    report = build_review(dataset, rubric, [record])
    assert report["cases"][0]["missing_company_mentions"] == ["FPT Software"]
    vietnamese = dataset.cases[1]
    vi_record = deepcopy(record)
    vi_record["case_id"] = vietnamese.id
    vi_record["input"]["origin_key"] = vietnamese.id
    vi_record["input"]["payload"]["subject"] = vietnamese.email.subject
    vi_record["input"]["payload"]["body"] = vietnamese.email.body
    vi_record["output"]["unknowns"] = ["Meeting details not supplied"]
    paired = build_review(dataset, rubric, [record, vi_record])["pairs"][0]
    assert paired["relevance_equal"] is True
    assert paired["unknowns_presence_equal"] is False
    assert paired["company_names_equal"] is True
    record["input"]["payload"]["body"] = "Changed input"
    with pytest.raises(EvaluationInputError):
        build_review(dataset, rubric, [record])
    record["input"]["payload"]["body"] = case.email.body
    record["input"]["payload"]["meeting_state"] = "cancelled"
    with pytest.raises(EvaluationInputError):
        build_review(dataset, rubric, [record])


def test_cli_sanitizes_invalid_private_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dataset = load_dataset(ROOT)
    log = tmp_path / "input.jsonl"
    log.write_text(
        json.dumps({"type": "run", "dataset_hash": dataset.content_hash()})
        + "\n"
        + json.dumps(
            {
                "type": "case",
                "case_id": dataset.cases[0].id,
                "status": "valid",
                "input": {"private": "PRIVATE-CANARY"},
            }
        )
        + "\n"
    )
    monkeypatch.setattr(
        "sys.argv", ["review", "--dataset", str(ROOT), "--log", str(log)]
    )
    with pytest.raises(SystemExit):
        main()
    assert "PRIVATE-CANARY" not in capsys.readouterr().err
