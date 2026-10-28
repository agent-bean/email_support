from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_live_smoke_without_private_config_reports_unsupported_safely(
    tmp_path: Path,
) -> None:
    output = tmp_path / "smoke.json"
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("RESEARCH_")
        and not key.startswith("OPENROUTER_")
        and not key.startswith("TAVILY_")
    }
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/smoke_research_providers.py",
            "--live",
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    assert completed.returncode == 2
    assert completed.stdout.strip() == (
        "research provider smoke: unsupported (configuration missing)"
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "unsupported"
    assert isinstance(report["working_tree_dirty"], bool)
    assert "RESEARCH_GATEWAY_API_KEY" in report["reason"]
    assert "secret" not in output.read_text(encoding="utf-8").lower()
    assert output.stat().st_mode & 0o777 == 0o600
