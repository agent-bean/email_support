"""Command-boundary checks for the opt-in owner runtime script."""

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = PROJECT_ROOT / "scripts/local-auth.sh"
BACKEND_DOCKERFILE = PROJECT_ROOT / "apps/backend/Dockerfile"
BACKEND_DOCKERIGNORE = PROJECT_ROOT / "apps/backend/.dockerignore"


def runtime_directory(
    tmp_path: Path, *, mode: int = 0o600, google_token_key: str | None = None
) -> Path:
    root = tmp_path / ".local-auth"
    root.mkdir(mode=0o700)
    config = root / "owner.conf"
    values = [
        "EMAIL_SUPPORT_OWNER_SUB=test-owner",
        "EMAIL_SUPPORT_GOOGLE_CLIENT_ID=test-client",
        "EMAIL_SUPPORT_GOOGLE_CLIENT_SECRET=test-secret-value",
        "EMAIL_SUPPORT_GOOGLE_CALLBACK_URI=http://127.0.0.1:8000/api/auth/google/callback",
        "EMAIL_SUPPORT_WEB_ORIGIN=http://127.0.0.1:5173",
    ]
    if google_token_key is not None:
        values.append(f"EMAIL_SUPPORT_GOOGLE_TOKEN_ENCRYPTION_KEY={google_token_key}")
    config.write_text("\n".join(values) + "\n", encoding="utf-8")
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
        print('api' if mode == 'smoke' else 'auth-postgres')
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
    if mode.startswith('recovery') and args[-1] == 'api':
        print('' if mode == 'recovery' else 'api-container')
    else:
        print('owned-container')
elif 'heads' in args:
    print('e7a21c4f9b30 (head)')
elif 'psql' in ' '.join(args):
    if '-f -' in ' '.join(args):
        query = sys.stdin.read()
        stdin_log = os.environ.get('FAKE_DOCKER_STDIN_LOG')
        if stdin_log:
            with open(stdin_log, 'a', encoding='utf-8') as sql_log:
                sql_log.write(query)
    else:
        query = args[-1]
    if mode == 'recovery' and 'SELECT revoke_operation_id' in query:
        print('5e93b29f-ff68-40ea-98e8-6078c7010078')
    elif mode == 'recovery' and 'UPDATE google_connections' in query:
        print('5e93b29f-ff68-40ea-98e8-6078c7010078')
    if mode == 'query-failure' and 'to_regclass' in query:
        sys.exit(1)
    elif mode == 'recovery' and (
        'SELECT revoke_operation_id' in query or 'UPDATE google_connections' in query
    ):
        pass
    elif 'to_regclass' in query:
        print('t' if mode in {'head', 'phase2'} else 'f')
    elif 'information_schema.tables' in query:
        print('0')
    else:
        print(
            'e7a21c4f9b30'
            if mode == 'head'
            else 'b17e9a4d2c61'
            if mode == 'phase2'
            else 'da3c8e14f627'
        )
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


def test_up_builds_current_migration_image_before_applying_schema(
    tmp_path: Path,
) -> None:
    runtime_directory(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _, log = fake_docker(bin_dir)
    ss = bin_dir / "ss"
    ss.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    ss.chmod(0o700)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "FAKE_DOCKER_LOG": str(log),
            "FAKE_DOCKER_MODE": "phase2",
        }
    )

    result = subprocess.run(
        [str(SCRIPT), "up"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    build_index = next(
        index for index, call in enumerate(calls) if " build api web" in call
    )
    heads_index = next(index for index, call in enumerate(calls) if "heads" in call)
    dump_index = next(index for index, call in enumerate(calls) if "pg_dump" in call)
    verify_index = next(
        index for index, call in enumerate(calls) if "pg_restore" in call
    )
    upgrade_index = next(
        index for index, call in enumerate(calls) if "upgrade head" in call
    )
    api_up_index = next(
        index
        for index, call in enumerate(calls)
        if " up --detach --wait --wait-timeout 90 api web" in call
    )
    assert build_index < heads_index < dump_index < verify_index < upgrade_index
    assert upgrade_index < api_up_index


def test_smoke_requires_a_private_encryption_key_before_docker(tmp_path: Path) -> None:
    runtime_directory(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _, log = fake_docker(bin_dir)
    env = os.environ.copy()
    env.update(
        {"PATH": f"{bin_dir}{os.pathsep}{env['PATH']}", "FAKE_DOCKER_LOG": str(log)}
    )

    result = subprocess.run(
        [str(SCRIPT), "smoke"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "encryption key" in result.stderr
    assert not log.exists()


def test_smoke_runs_only_in_the_owned_api_container(tmp_path: Path) -> None:
    runtime_directory(tmp_path, google_token_key="test-private-fernet-key")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _, log = fake_docker(bin_dir)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "FAKE_DOCKER_LOG": str(log),
            "FAKE_DOCKER_MODE": "smoke",
        }
    )

    result = subprocess.run(
        [str(SCRIPT), "smoke"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        input="",
    )

    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    assert any("ps --status running --quiet api" in call for call in calls)
    assert any("live-google-smoke.py" in call for call in calls)


def test_backend_image_includes_the_live_smoke_harness() -> None:
    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")
    dockerignore = BACKEND_DOCKERIGNORE.read_text(encoding="utf-8")

    expected_copy = (
        "COPY --chown=app:app scripts/live-google-smoke.py "
        "./scripts/live-google-smoke.py"
    )
    assert expected_copy in dockerfile
    assert "!scripts/" in dockerignore
    assert "!scripts/live-google-smoke.py" in dockerignore


def test_resolve_revoke_requires_exact_operation_and_updates_only_purged_unknown(
    tmp_path: Path,
) -> None:
    runtime_directory(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _, log = fake_docker(bin_dir)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "FAKE_DOCKER_LOG": str(log),
            "FAKE_DOCKER_STDIN_LOG": str(tmp_path / "docker-stdin.log"),
            "FAKE_DOCKER_MODE": "recovery",
        }
    )

    result = subprocess.run(
        [str(SCRIPT), "resolve-revoke"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        input="REMOVED\n5e93b29f-ff68-40ea-98e8-6078c7010078\n",
    )

    assert result.returncode == 0, result.stderr
    assert "revoke marker resolved" in result.stdout
    calls = log.read_text(encoding="utf-8").splitlines()
    assert any("-Atq -f -" in call for call in calls)
    supplied_sql = (tmp_path / "docker-stdin.log").read_text(encoding="utf-8")
    assert ":'owner_sub'" in supplied_sql
    assert ":'operation_id'" in supplied_sql
    assert "UPDATE google_connections" in supplied_sql
    assert "revoke_operation_id" in supplied_sql
    assert "revoke_state IN ('in_progress', 'unknown')" in supplied_sql
    assert "encrypted_token_bundle IS NULL" in supplied_sql


def test_resolve_revoke_stops_when_operator_does_not_confirm_cleanup(
    tmp_path: Path,
) -> None:
    runtime_directory(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _, log = fake_docker(bin_dir)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "FAKE_DOCKER_LOG": str(log),
            "FAKE_DOCKER_MODE": "recovery",
        }
    )

    result = subprocess.run(
        [str(SCRIPT), "resolve-revoke"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        input="NO\n",
    )

    assert result.returncode != 0
    assert "operator confirmation" in result.stderr
    assert not any(
        "UPDATE google_connections" in call
        for call in log.read_text(encoding="utf-8").splitlines()
    )


def test_resolve_revoke_requires_the_exact_pending_operation_id(
    tmp_path: Path,
) -> None:
    runtime_directory(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _, log = fake_docker(bin_dir)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "FAKE_DOCKER_LOG": str(log),
            "FAKE_DOCKER_MODE": "recovery",
        }
    )

    result = subprocess.run(
        [str(SCRIPT), "resolve-revoke"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        input="REMOVED\n00000000-0000-0000-0000-000000000000\n",
    )

    assert result.returncode != 0
    assert "operation ID did not match" in result.stderr
    assert not any(
        "UPDATE google_connections" in call
        for call in log.read_text(encoding="utf-8").splitlines()
    )


def test_resolve_revoke_waits_for_the_owner_api_to_stop(
    tmp_path: Path,
) -> None:
    runtime_directory(tmp_path)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _, log = fake_docker(bin_dir)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "FAKE_DOCKER_LOG": str(log),
            "FAKE_DOCKER_MODE": "recovery-running-api",
        }
    )

    result = subprocess.run(
        [str(SCRIPT), "resolve-revoke"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        input="REMOVED\n",
    )

    assert result.returncode != 0
    assert "could not stop the owner API" in result.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    assert any("stop --timeout 10 api" in call for call in calls)
    assert not any("SELECT revoke_operation_id" in call for call in calls)
