from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).parents[2]
DATASET = BACKEND / "evals" / "datasets" / "briefing-v1"


def _run(*arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    environment.pop("OPENROUTER_API_KEY", None)
    environment.pop("TAVILY_API_KEY", None)
    return subprocess.run(
        [sys.executable, "-m", "evals", *arguments],
        cwd=BACKEND,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
        timeout=20,
    )


def test_cli_self_check_runs_and_reports_oracle_result() -> None:
    result = _run("self-check")
    assert result.returncode == 0, result.stderr
    assert "oracle: passed" in result.stdout


def test_cli_validate_loads_all_ten_scenarios_without_provider_credentials() -> None:
    result = _run("validate", "--dataset", str(DATASET))
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["case_count"] == 20
    assert report["candidate_count"] == 20
    assert report["languages"] == {"en": 10, "vi": 10}
    assert report["source_count"] >= 1


def test_cli_reports_malformed_dataset_safely(tmp_path: Path) -> None:
    dataset = tmp_path / "bad-dataset"
    dataset.mkdir()
    (dataset / "cases.json").write_text('{"cases": [\n', encoding="utf-8")
    (dataset / "sources.json").write_text('{"sources": []}', encoding="utf-8")

    result = _run("validate", "--dataset", str(dataset))
    assert result.returncode != 0
    assert "Invalid dataset" in result.stderr
    assert "Traceback" not in result.stderr
    assert "cases.json" in result.stderr


def test_cli_self_check_fails_when_oracle_expectation_is_inverted(
    tmp_path: Path,
) -> None:
    oracle = BACKEND / "evals" / "fixtures" / "evaluator-oracle.json"
    fixture = json.loads(oracle.read_text(encoding="utf-8"))
    fixture["assertions"][0]["expected_support"] = "unsupported"
    bad_oracle = tmp_path / "inverted-oracle.json"
    bad_oracle.write_text(json.dumps(fixture), encoding="utf-8")

    result = _run("self-check", "--oracle", str(bad_oracle))
    assert result.returncode == 1
    assert "oracle: failed" in result.stderr


def test_cli_reports_invalid_utf8_oracle_without_traceback(tmp_path: Path) -> None:
    oracle = tmp_path / "invalid-oracle.json"
    oracle.write_bytes(b"\xff")
    result = _run("self-check", "--oracle", str(oracle))
    assert result.returncode == 2
    assert "Invalid evaluator oracle" in result.stderr
    assert "Traceback" not in result.stderr


def test_live_command_is_explicitly_unsupported_until_production_adapter_exists() -> (
    None
):
    result = _run("live")
    assert result.returncode == 2
    assert "unsupported" in result.stderr.lower()


def test_replay_is_repeatable_and_output_omits_claim_text(tmp_path: Path) -> None:
    private_claim = "Private mailbox canary: do not disclose this string."
    capture = tmp_path / "capture.json"
    capture.write_text(
        json.dumps(
            {
                "dataset_version": "briefing-v1",
                "application_revision": "a" * 40,
                "prompt_version": "prompt-v1",
                "model_id": "offline-capture",
                "config_hash": "b" * 64,
                "cases": [
                    {
                        "case_id": "stale-sources-en",
                        "claims": [
                            {
                                "id": "adobe-mission",
                                "kind": "fact",
                                "text": private_claim,
                                "evidence_ids": ["adobe-about"],
                            }
                        ],
                        "attempts": [
                            {
                                "attempt": 1,
                                "input_tokens": None,
                                "output_tokens": None,
                                "cost_usd": None,
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    outputs = [tmp_path / "one.json", tmp_path / "two.json"]
    for output in outputs:
        result = _run(
            "replay",
            "--dataset",
            str(DATASET),
            "--results",
            str(capture),
            "--output",
            str(output),
        )
        assert result.returncode == 0, result.stderr
        assert output.exists()

    reports = [json.loads(path.read_text(encoding="utf-8")) for path in outputs]
    assert reports[0]["run"]["case_results"] == reports[1]["run"]["case_results"]
    replayed_case = next(
        item
        for item in reports[0]["run"]["case_results"]
        if item["case_id"] == "stale-sources-en"
    )
    assert replayed_case["status"] == "review_pending"
    assert replayed_case["attempts"][0]["input_tokens"] is None
    assert private_claim not in outputs[0].read_text(encoding="utf-8")


def test_replay_reports_stale_review_binding_without_traceback(tmp_path: Path) -> None:
    capture = tmp_path / "capture.json"
    capture.write_text(
        json.dumps(
            {
                "dataset_version": "briefing-v1",
                "application_revision": "a" * 40,
                "prompt_version": "prompt-v1",
                "model_id": "offline-capture",
                "config_hash": "b" * 64,
                "cases": [{"case_id": "stale-sources-en"}],
            }
        ),
        encoding="utf-8",
    )
    review = tmp_path / "stale-review.json"
    review.write_text(
        json.dumps(
            {
                "run_id": "another-run",
                "dataset_version": "briefing-v1",
                "run_hash": "c" * 64,
                "source_hashes": {},
                "reviewer": "owner",
                "reviewed_at": "2026-10-27T07:20:00Z",
            }
        ),
        encoding="utf-8",
    )
    result = _run(
        "replay",
        "--dataset",
        str(DATASET),
        "--results",
        str(capture),
        "--review",
        str(review),
        "--output",
        str(tmp_path / "out.json"),
    )
    assert result.returncode == 2
    assert "Review binding failed" in result.stderr
    assert "Traceback" not in result.stderr


def test_replay_reports_output_parent_file_without_traceback(tmp_path: Path) -> None:
    capture = tmp_path / "capture.json"
    capture.write_text(
        json.dumps(
            {
                "dataset_version": "briefing-v1",
                "application_revision": "a" * 40,
                "prompt_version": "prompt-v1",
                "model_id": "offline-capture",
                "config_hash": "b" * 64,
                "cases": [{"case_id": "stale-sources-en"}],
            }
        ),
        encoding="utf-8",
    )
    output_parent = tmp_path / "not-a-directory"
    output_parent.write_text("file", encoding="utf-8")
    result = _run(
        "replay",
        "--dataset",
        str(DATASET),
        "--results",
        str(capture),
        "--output",
        str(output_parent / "run.json"),
    )
    assert result.returncode == 2
    assert "Output could not be written" in result.stderr
    assert "Traceback" not in result.stderr
