"""Command-boundary checks for the opt-in owner runtime script."""

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = PROJECT_ROOT / "scripts/local-auth.sh"


def runtime_directory(tmp_path: Path, *, mode: int = 0o600) -> Path:
    root = tmp_path / ".local-auth"
    root.mkdir(mode=0o700)
    config = root / "owner.conf"
    config.write_text(
        "\n".join(
            (
                "EMAIL_SUPPORT_OWNER_SUB=test-owner",
                "EMAIL_SUPPORT_GOOGLE_CLIENT_ID=test-client",
                "EMAIL_SUPPORT_GOOGLE_CLIENT_SECRET=test-secret-value",
                "EMAIL_SUPPORT_GOOGLE_CALLBACK_URI=http://127.0.0.1:8000/api/auth/google/callback",
                "EMAIL_SUPPORT_WEB_ORIGIN=http://127.0.0.1:5173",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    config.chmod(mode)
    return root


def fake_docker(directory: Path) -> tuple[Path, Path]:
    binary = directory / "docker"
    log = directory / "docker.log"
    binary.write_text(
        """#!/usr/bin/env python3
import os
import sys

args = sys.argv[1:]
with open(os.environ['FAKE_DOCKER_LOG'], 'a', encoding='utf-8') as log:
    log.write(' '.join(args) + '\\n')
mode = os.environ.get('FAKE_DOCKER_MODE', 'initial')
if args and args[0] == 'inspect':
    template = args[2]
    if 'com.docker.compose.project' in template:
        print('wrong-project' if mode == 'foreign' else 'email-support-auth-local')
    elif 'com.docker.compose.service' in template:
        print('auth-postgres')
    elif 'com.email_support.local_auth' in template:
        print('true')
    else:
        data_dir = (
            '.test-database/postgres-data'
            if mode == 'test-database'
            else '.local-auth/postgres-data'
        )
        print(os.path.join(os.getcwd(), data_dir))
elif 'ps' in args and '--status' in args:
    print('owned-container')
elif 'heads' in args:
    print('b17e9a4d2c61 (head)')
elif 'psql' in ' '.join(args):
    query = args[-1]
    if mode == 'query-failure' and 'to_regclass' in query:
        sys.exit(1)
    if 'to_regclass' in query:
        print('t' if mode == 'head' else 'f')
    elif 'information_schema.tables' in query:
        print('0')
    else:
        print('b17e9a4d2c61' if mode == 'head' else 'da3c8e14f627')
elif 'pg_dump' in ' '.join(args):
    sys.stdout.buffer.write(b'custom archive fixture')
elif 'pg_restore' in args:
    if mode == 'backup-invalid':
        sys.exit(1)
elif 'upgrade' in args:
    pass
""",
        encoding="utf-8",
    )
    binary.chmod(0o700)
    return binary, log


def run_runtime(
    tmp_path: Path, mode: str = "initial"
) -> tuple[subprocess.CompletedProcess[str], list[str], Path]:
    root = runtime_directory(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _, log = fake_docker(bin_dir)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "FAKE_DOCKER_LOG": str(log),
            "FAKE_DOCKER_MODE": mode,
        }
    )
    result = subprocess.run(
        [str(SCRIPT), "migrate"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    return result, calls, root


def test_initial_install_validates_private_backup_before_upgrade(
    tmp_path: Path,
) -> None:
    result, calls, root = run_runtime(tmp_path)

    assert result.returncode == 0, result.stderr
    dump_index = next(index for index, call in enumerate(calls) if "pg_dump" in call)
    verify_index = next(
        index for index, call in enumerate(calls) if "pg_restore" in call
    )
    upgrade_index = next(
        index for index, call in enumerate(calls) if "upgrade head" in call
    )
    assert dump_index < verify_index < upgrade_index
    archives = list((root / "backups").glob("*.dump"))
    assert len(archives) == 1
    assert archives[0].stat().st_mode & 0o777 == 0o600


def test_current_head_is_a_noop_without_backup_or_migration(tmp_path: Path) -> None:
    result, calls, _ = run_runtime(tmp_path, "head")

    assert result.returncode == 0, result.stderr
    assert not any("pg_dump" in call or "upgrade head" in call for call in calls)


@pytest.mark.parametrize("mode", ["foreign", "query-failure"])
def test_unsafe_identity_or_failed_revision_query_stops_before_migration(
    tmp_path: Path, mode: str
) -> None:
    result, calls, _ = run_runtime(tmp_path, mode)

    assert result.returncode != 0
    assert not any("pg_dump" in call or "upgrade head" in call for call in calls)


def test_test_database_mount_is_refused(tmp_path: Path) -> None:
    result, calls, _ = run_runtime(tmp_path, "test-database")

    assert result.returncode != 0
    assert not any("pg_dump" in call or "upgrade head" in call for call in calls)


def test_invalid_backup_is_retained_and_blocks_migration(tmp_path: Path) -> None:
    result, calls, root = run_runtime(tmp_path, "backup-invalid")

    assert result.returncode != 0
    assert not any("upgrade head" in call for call in calls)
    assert len(list((root / "backups").glob("*.dump"))) == 1


def test_insecure_private_config_is_refused_before_docker(tmp_path: Path) -> None:
    runtime_directory(tmp_path, mode=0o644)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _, log = fake_docker(bin_dir)
    env = os.environ.copy()
    env.update(
        {"PATH": f"{bin_dir}{os.pathsep}{env['PATH']}", "FAKE_DOCKER_LOG": str(log)}
    )

    result = subprocess.run(
        [str(SCRIPT), "migrate"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not log.exists()
    assert "mode 0600" in result.stderr


def test_private_runtime_root_cannot_be_a_symlink(tmp_path: Path) -> None:
    target = tmp_path / "external"
    target.mkdir()
    (tmp_path / ".local-auth").symlink_to(target, target_is_directory=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _, log = fake_docker(bin_dir)
    env = os.environ.copy()
    env.update(
        {"PATH": f"{bin_dir}{os.pathsep}{env['PATH']}", "FAKE_DOCKER_LOG": str(log)}
    )

    result = subprocess.run(
        [str(SCRIPT), "migrate"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not log.exists()
    assert "symbolic link" in result.stderr


def test_up_refuses_an_unrelated_listener_on_the_documented_port(
    tmp_path: Path,
) -> None:
    runtime_directory(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _, log = fake_docker(bin_dir)
    ss = bin_dir / "ss"
    ss.write_text("#!/bin/sh\nprintf 'LISTEN\\n'\n", encoding="utf-8")
    ss.chmod(0o700)
    env = os.environ.copy()
    env.update(
        {"PATH": f"{bin_dir}{os.pathsep}{env['PATH']}", "FAKE_DOCKER_LOG": str(log)}
    )

    result = subprocess.run(
        [str(SCRIPT), "up"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert not any(
        " up " in call for call in log.read_text(encoding="utf-8").splitlines()
    )
    assert "port 5173 is occupied" in result.stderr
