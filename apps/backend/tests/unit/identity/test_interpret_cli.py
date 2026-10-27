from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from scripts.interpret_email import _write_private_json


def test_cli_output_is_private_and_exclusive(tmp_path: Path) -> None:
    output = tmp_path / "interpretation.json"
    _write_private_json(output, {"status": "unresolved"})

    assert json.loads(output.read_text(encoding="utf-8")) == {"status": "unresolved"}
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        _write_private_json(output, {"status": "overwritten"})


def test_cli_output_does_not_follow_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("private", encoding="utf-8")
    output = tmp_path / "result.json"
    output.symlink_to(target)

    with pytest.raises(OSError):
        _write_private_json(output, {"status": "unresolved"})
    assert target.read_text(encoding="utf-8") == "private"
