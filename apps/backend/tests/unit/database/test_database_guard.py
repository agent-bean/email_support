import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import BinaryIO, cast

import pytest
from sqlalchemy.engine import make_url

import scripts.test_database as test_database
from scripts.test_database import (
    DatabaseIdentity,
    DatabaseLifecycle,
    require_test_database_url,
    run_guarded_mutation,
    validate_target_identity,
    verify_github_actions_container,
    verify_owned_container,
)
from scripts.test_database import (
    TestDatabaseGuardError as DatabaseGuardError,
)


def test_database_url_is_required_and_must_not_be_an_application_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("EMAIL_SUPPORT_TEST_DATABASE_URL", raising=False)
    with pytest.raises(DatabaseGuardError):
        require_test_database_url()

    monkeypatch.setenv(
        "EMAIL_SUPPORT_TEST_DATABASE_URL",
        "postgresql+psycopg://app:pw@localhost:5432/email_support",
    )
    with pytest.raises(DatabaseGuardError):
        require_test_database_url()


def test_guard_requires_exact_database_role_and_owned_server_identity() -> None:
    expected = DatabaseIdentity(
        database="email_support_test_run_001_storage_001",
        role="email_support_test_admin",
        container_id="a" * 64,
        server_identifier="7341226101234567890",
    )
    validate_target_identity(expected, expected)

    for actual in (
        replace(expected, database="email_support"),
        replace(expected, role="app"),
        replace(expected, container_id="b" * 64),
        replace(expected, server_identifier="1"),
    ):
        with pytest.raises(DatabaseGuardError):
            validate_target_identity(actual, expected)


def test_failed_backup_stops_before_mutation_and_retains_recovery_data(
    tmp_path: Path,
) -> None:
    mutations: list[str] = []
    recovery_path = tmp_path / "recovery"
    recovery_path.mkdir(mode=0o700)

    def fail_backup() -> None:
        raise DatabaseGuardError("dump verification failed")

    with pytest.raises(DatabaseGuardError, match="dump verification failed"):
        run_guarded_mutation(
            backup=fail_backup,
            mutation=lambda: mutations.append("mutated"),
            recovery_path=recovery_path,
        )

    assert mutations == []
    assert recovery_path.is_dir()


def test_shutdown_cleanup_command_dispatches_to_database_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LifecycleStub:
        def __init__(self) -> None:
            self.shutdown_called = False

        def shutdown_cleanup(self) -> None:
            self.shutdown_called = True

    lifecycle = LifecycleStub()
    monkeypatch.setattr(
        sys,
        "argv",
        ["test_database.py", "shutdown-cleanup"],
    )
    monkeypatch.setattr(test_database, "_lifecycle", lambda: lifecycle)

    assert test_database.main() == 0
    assert lifecycle.shutdown_called


def test_container_guard_rejects_a_service_with_the_wrong_owner_label(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    container_id = "a" * 64
    data_directory = tmp_path / "postgres-data"
    data_directory.mkdir(mode=0o700)
    monkeypatch.setenv("EMAIL_SUPPORT_TEST_DATA_DIR", str(data_directory))
    monkeypatch.setattr(
        test_database,
        "_compose_config",
        lambda *_: {
            "services": {
                "postgres": {
                    "image": "postgres:18.6-bookworm@sha256:" + "b" * 64,
                    "user": "1000:1000",
                }
            }
        },
    )
    record = {
        "Id": container_id,
        "Config": {
            "Image": "postgres:18.6-bookworm@sha256:" + "b" * 64,
            "User": "1000:1000",
            "Labels": {
                "com.docker.compose.project": "email-support-test",
                "com.docker.compose.service": "postgres",
                "com.email_support.test_database": "false",
            },
        },
        "State": {"Running": True},
        "NetworkSettings": {
            "Ports": {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": "55432"}]}
        },
        "Mounts": [
            {
                "Type": "bind",
                "Source": str(data_directory),
                "Destination": "/var/lib/postgresql",
            }
        ],
    }
    monkeypatch.setattr(
        test_database,
        "_run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["docker", "inspect"],
            returncode=0,
            stdout=json.dumps([record]),
            stderr="",
        ),
    )

    with pytest.raises(DatabaseGuardError, match="not the owned"):
        verify_owned_container(
            container_id=container_id,
            compose_file=tmp_path / "compose.test.yaml",
            project_name="email-support-test",
            expected_port=55432,
        )


def test_github_actions_container_guard_requires_the_exact_healthy_database_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    container_id = "a" * 64
    image = "postgres:18.6-bookworm@sha256:" + "b" * 64
    monkeypatch.setattr(
        test_database,
        "_compose_config",
        lambda *_: {"services": {"postgres": {"image": image}}},
    )
    record = {
        "Id": container_id,
        "Config": {
            "Image": image,
            "Env": [
                "POSTGRES_USER=email_support_test_admin",
                "POSTGRES_DB=postgres",
            ],
        },
        "State": {"Running": True, "Health": {"Status": "healthy"}},
        "NetworkSettings": {"Ports": {"5432/tcp": [{"HostPort": "55432"}]}},
    }
    monkeypatch.setattr(
        test_database,
        "_run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["docker", "inspect"],
            returncode=0,
            stdout=json.dumps([record]),
            stderr="",
        ),
    )

    assert (
        verify_github_actions_container(
            container_id=container_id,
            compose_file=tmp_path / "compose.test.yaml",
            project_name="email-support-test",
            expected_port=55432,
        )
        == container_id
    )


def test_github_actions_container_guard_rejects_a_different_mapped_port(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    container_id = "a" * 64
    image = "postgres:18.6-bookworm@sha256:" + "b" * 64
    monkeypatch.setattr(
        test_database,
        "_compose_config",
        lambda *_: {"services": {"postgres": {"image": image}}},
    )
    record: dict[str, object] = {
        "Id": container_id,
        "Config": {
            "Image": image,
            "Env": [
                "POSTGRES_USER=email_support_test_admin",
                "POSTGRES_DB=postgres",
            ],
        },
        "State": {"Running": True, "Health": {"Status": "healthy"}},
        "NetworkSettings": {"Ports": {"5432/tcp": [{"HostPort": "55433"}]}},
    }
    monkeypatch.setattr(
        test_database,
        "_run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=["docker", "inspect"],
            returncode=0,
            stdout=json.dumps([record]),
            stderr="",
        ),
    )

    with pytest.raises(DatabaseGuardError, match="CI PostgreSQL service"):
        verify_github_actions_container(
            container_id=container_id,
            compose_file=tmp_path / "compose.test.yaml",
            project_name="email-support-test",
            expected_port=55432,
        )


def test_ownership_allowlist_rejects_symlinks(tmp_path: Path) -> None:
    recovery_path = tmp_path / "recovery"
    recovery_path.mkdir(mode=0o700)
    external_state = tmp_path / "outside-state.json"
    external_state.write_text('{"counter":0,"targets":[]}', encoding="utf-8")
    (tmp_path / "owned-targets.json").symlink_to(external_state)

    with pytest.raises(DatabaseGuardError, match="regular file"):
        DatabaseLifecycle(
            database_url=make_url(
                "postgresql+psycopg://email_support_test_admin:secret@127.0.0.1:55432/postgres"
            ),
            container_id="a" * 64,
            server_identifier="7341226101234567890",
            backup_root=recovery_path,
            run_id="1234abcd",
            compose_file=tmp_path / "compose.test.yaml",
            project_name="email-support-test",
            expected_port=55432,
        )


@pytest.mark.parametrize("failure_stage", ["dump", "list"])
def test_failed_dump_or_archive_verification_blocks_mutation_and_keeps_recovery(
    failure_stage: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recovery_path = tmp_path / "recovery"
    recovery_path.mkdir(mode=0o700)
    lifecycle = DatabaseLifecycle(
        database_url=make_url(
            "postgresql+psycopg://email_support_test_admin:secret@127.0.0.1:55432/postgres"
        ),
        container_id="a" * 64,
        server_identifier="7341226101234567890",
        backup_root=recovery_path,
        run_id="1234abcd",
        compose_file=tmp_path / "compose.test.yaml",
        project_name="email-support-test",
        expected_port=55432,
    )
    monkeypatch.setattr(lifecycle, "_verify_identity", lambda _database: None)
    mutations: list[str] = []

    def fail_at_selected_stage(
        args: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if "pg_dump" in args and failure_stage == "list":
            cast(BinaryIO, kwargs["stdout"]).write(b"not a real archive")
            return subprocess.CompletedProcess(
                args=args, returncode=0, stdout="", stderr=""
            )
        failed = ("pg_dump" in args and failure_stage == "dump") or (
            "pg_restore" in args and failure_stage == "list"
        )
        return subprocess.CompletedProcess(
            args=args, returncode=1 if failed else 0, stdout="", stderr="failed"
        )

    monkeypatch.setattr(subprocess, "run", fail_at_selected_stage)
    expected_error = "pg_dump failed" if failure_stage == "dump" else "pg_restore list"
    with pytest.raises(DatabaseGuardError, match=expected_error):
        run_guarded_mutation(
            backup=lambda: lifecycle.backup_database("postgres", "failure-test"),
            mutation=lambda: mutations.append("mutated"),
            recovery_path=recovery_path,
        )

    assert mutations == []
    assert recovery_path.is_dir()
    assert len(list(recovery_path.glob("*.dump"))) == 1
