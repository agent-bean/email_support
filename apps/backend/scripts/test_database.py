"""Guarded PostgreSQL scenario, dump and restore helpers for database tests."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import psycopg
from sqlalchemy.engine import URL, make_url

TEST_DATABASE_URL = "EMAIL_SUPPORT_TEST_DATABASE_URL"
ALEMBIC_DATABASE_URL = "EMAIL_SUPPORT_ALEMBIC_DATABASE_URL"
TEST_ROLE = "email_support_test_admin"
CONTROL_DATABASE = "postgres"
TEST_DATABASE_PREFIX = "email_support_test_"
TEST_DATABASE_NAME = re.compile(
    r"^email_support_test_[0-9a-f]{8}_[0-9]{5}_[a-z0-9_]{1,24}$"
)
BACKEND_ROOT = Path(__file__).resolve().parents[1]


class TestDatabaseGuardError(RuntimeError):
    """A database target or mutation could not be proven safe."""


@dataclass(frozen=True)
class DatabaseIdentity:
    database: str
    role: str
    container_id: str
    server_identifier: str


def require_test_database_url() -> URL:
    """Require only the dedicated test control URL; never use an app URL fallback."""
    value = os.environ.get(TEST_DATABASE_URL)
    if not value:
        raise TestDatabaseGuardError(f"{TEST_DATABASE_URL} is required")
    try:
        url = make_url(value)
    except Exception as error:
        raise TestDatabaseGuardError(f"{TEST_DATABASE_URL} is invalid") from error
    if (
        url.drivername != "postgresql+psycopg"
        or url.username != TEST_ROLE
        or url.password is None
        or url.host not in {"127.0.0.1", "localhost"}
        or url.port != 55432
        or url.database != CONTROL_DATABASE
    ):
        raise TestDatabaseGuardError(
            f"{TEST_DATABASE_URL} must identify the local test control database"
        )
    return url


def validate_target_identity(
    actual: DatabaseIdentity, expected: DatabaseIdentity
) -> None:
    if actual != expected:
        raise TestDatabaseGuardError(
            "database identity did not match the verified test target "
            f"(database={actual.database!r}, role={actual.role!r}, "
            f"container={actual.container_id[:12]!r}, "
            f"server={actual.server_identifier!r})"
        )


def run_guarded_mutation(
    *,
    backup: Callable[[], object],
    mutation: Callable[[], object],
    recovery_path: Path,
) -> object:
    """Run a mutation only after a verified backup has completed."""
    if not recovery_path.is_dir():
        raise TestDatabaseGuardError("private recovery directory is unavailable")
    backup()
    return mutation()


def _run(
    args: Sequence[str], *, input_text: str | None = None
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(args),
            check=False,
            capture_output=True,
            text=True,
            input=input_text,
        )
    except OSError as error:
        raise TestDatabaseGuardError(
            "required database utility could not run"
        ) from error


def _compose_config(compose_file: Path, project_name: str) -> dict[str, object]:
    result = _run(
        [
            "docker",
            "compose",
            "--project-name",
            project_name,
            "--file",
            str(compose_file),
            "config",
            "--format",
            "json",
        ]
    )
    if result.returncode != 0:
        raise TestDatabaseGuardError("test Compose configuration is invalid")
    try:
        decoded = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise TestDatabaseGuardError(
            "test Compose configuration is unreadable"
        ) from error
    if not isinstance(decoded, dict):
        raise TestDatabaseGuardError("test Compose configuration is unreadable")
    return decoded


def _expected_postgres_image(compose_file: Path, project_name: str) -> str:
    config = _compose_config(compose_file, project_name)
    services = config.get("services")
    if not isinstance(services, dict) or not isinstance(services.get("postgres"), dict):
        raise TestDatabaseGuardError("test PostgreSQL service is not configured")
    image = services["postgres"].get("image")
    if not isinstance(image, str) or "@sha256:" not in image:
        raise TestDatabaseGuardError("test PostgreSQL image must use a pinned digest")
    return image


def verify_owned_container(
    *, container_id: str, compose_file: Path, project_name: str, expected_port: int
) -> str:
    """Prove a running container belongs to this Compose project and test service."""
    config = _compose_config(compose_file, project_name)
    services = config.get("services")
    if not isinstance(services, dict) or not isinstance(services.get("postgres"), dict):
        raise TestDatabaseGuardError("test PostgreSQL service is not configured")
    postgres_config = services["postgres"]
    expected_image = postgres_config.get("image")
    if not isinstance(expected_image, str) or "@sha256:" not in expected_image:
        raise TestDatabaseGuardError("test PostgreSQL image must use a pinned digest")
    expected_user = postgres_config.get("user")
    if not isinstance(expected_user, str) or not re.fullmatch(
        r"[1-9][0-9]*:[0-9]+", expected_user
    ):
        raise TestDatabaseGuardError(
            "test PostgreSQL service must use the private directory owner"
        )

    inspected = _run(["docker", "inspect", container_id])
    if inspected.returncode != 0:
        raise TestDatabaseGuardError("test PostgreSQL container could not be inspected")
    try:
        records = json.loads(inspected.stdout)
        record = records[0]
    except (json.JSONDecodeError, IndexError, TypeError, KeyError) as error:
        raise TestDatabaseGuardError(
            "test PostgreSQL container identity is unreadable"
        ) from error

    config_record = record.get("Config", {})
    labels = config_record.get("Labels", {})
    state = record.get("State", {})
    container_config = config_record.get("Image")
    actual_id = str(record.get("Id", ""))
    if (
        actual_id != container_id
        or state.get("Running") is not True
        or container_config != expected_image
        or config_record.get("User") != expected_user
        or labels.get("com.docker.compose.project") != project_name
        or labels.get("com.docker.compose.service") != "postgres"
        or labels.get("com.email_support.test_database") != "true"
    ):
        raise TestDatabaseGuardError(
            "container is not the owned PostgreSQL test service"
        )

    port_mappings = record.get("NetworkSettings", {}).get("Ports", {}).get("5432/tcp")
    if not isinstance(port_mappings, list) or not any(
        mapping.get("HostIp") == "127.0.0.1"
        and mapping.get("HostPort") == str(expected_port)
        for mapping in port_mappings
    ):
        raise TestDatabaseGuardError(
            "test service is not bound to its expected loopback port"
        )

    data_directory = os.environ.get("EMAIL_SUPPORT_TEST_DATA_DIR")
    mounts = record.get("Mounts", [])
    if not data_directory or not any(
        Path(str(mount.get("Source", ""))).resolve() == Path(data_directory).resolve()
        and mount.get("Destination") == "/var/lib/postgresql"
        and mount.get("Type") == "bind"
        for mount in mounts
    ):
        raise TestDatabaseGuardError(
            "test service is not using its retained private data directory"
        )

    return actual_id


def verify_github_actions_container(
    *, container_id: str, compose_file: Path, project_name: str, expected_port: int
) -> str:
    """Verify the exact PostgreSQL service container supplied by GitHub Actions."""
    if not re.fullmatch(r"[a-f0-9]{64}", container_id):
        raise TestDatabaseGuardError(
            "GitHub Actions PostgreSQL container ID is invalid"
        )

    expected_image = _expected_postgres_image(compose_file, project_name)
    inspected = _run(["docker", "inspect", container_id])
    if inspected.returncode != 0:
        raise TestDatabaseGuardError(
            "GitHub Actions PostgreSQL container could not be inspected"
        )
    try:
        records = json.loads(inspected.stdout)
        record = records[0]
    except (json.JSONDecodeError, IndexError, TypeError, KeyError) as error:
        raise TestDatabaseGuardError(
            "GitHub Actions PostgreSQL container identity is unreadable"
        ) from error

    config_record = record.get("Config", {})
    state = record.get("State", {})
    network = record.get("NetworkSettings", {})
    actual_id = str(record.get("Id", ""))
    configured_env = config_record.get("Env", [])
    health = state.get("Health", {})
    required_env = {
        f"POSTGRES_USER={TEST_ROLE}",
        f"POSTGRES_DB={CONTROL_DATABASE}",
    }
    port_mappings = network.get("Ports", {}).get("5432/tcp")
    if (
        actual_id != container_id
        or state.get("Running") is not True
        or health.get("Status") != "healthy"
        or config_record.get("Image") != expected_image
        or not isinstance(configured_env, list)
        or not required_env.issubset(configured_env)
        or not isinstance(port_mappings, list)
        or not any(
            mapping.get("HostPort") == str(expected_port) for mapping in port_mappings
        )
    ):
        raise TestDatabaseGuardError("container is not the CI PostgreSQL service")
    return actual_id


def _url_for_database(url: URL, database: str) -> URL:
    return url.set(database=database, drivername="postgresql")


def _server_identity(url: URL) -> tuple[str, str, str]:
    if not url.database:
        raise TestDatabaseGuardError("test database identity requires a database name")
    try:
        with psycopg.connect(
            _url_for_database(url, url.database).render_as_string(hide_password=False),
            connect_timeout=5,
        ) as connection:
            row = connection.execute(
                "SELECT current_database(), current_user, "
                "system_identifier::text FROM pg_control_system()"
            ).fetchone()
    except psycopg.Error as error:
        raise TestDatabaseGuardError("test server identity query failed") from error
    if row is None:
        raise TestDatabaseGuardError("test server identity query returned no row")
    database, role, server_identifier = (str(value) for value in row)
    return database, role, server_identifier


def _server_identifier_in_container(container_id: str) -> str:
    result = _run(
        [
            "docker",
            "exec",
            container_id,
            "psql",
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            "--username",
            TEST_ROLE,
            "--dbname",
            CONTROL_DATABASE,
            "--command",
            "SELECT system_identifier::text FROM pg_control_system()",
        ]
    )
    if result.returncode != 0:
        raise TestDatabaseGuardError("owned PostgreSQL server identity query failed")
    identifier = result.stdout.strip()
    if not identifier.isdecimal():
        raise TestDatabaseGuardError("owned PostgreSQL server identity is invalid")
    return identifier


def verify_service(
    *,
    container_id: str,
    compose_file: Path,
    project_name: str,
    expected_port: int,
    service_kind: str = "compose",
) -> str:
    url = require_test_database_url()
    if service_kind == "compose":
        verified_container_id = verify_owned_container(
            container_id=container_id,
            compose_file=compose_file,
            project_name=project_name,
            expected_port=expected_port,
        )
    elif service_kind == "github-actions":
        verified_container_id = verify_github_actions_container(
            container_id=container_id,
            compose_file=compose_file,
            project_name=project_name,
            expected_port=expected_port,
        )
    else:
        raise TestDatabaseGuardError("test PostgreSQL service kind is invalid")
    database, role, url_server_identifier = _server_identity(url)
    container_server_identifier = _server_identifier_in_container(verified_container_id)
    if (
        database != CONTROL_DATABASE
        or role != TEST_ROLE
        or url_server_identifier != container_server_identifier
    ):
        raise TestDatabaseGuardError(
            "test URL does not reach the owned PostgreSQL server"
        )
    return container_server_identifier


class DatabaseLifecycle:
    """Create, back up, restore and remove only allowlisted scenario databases."""

    def __init__(
        self,
        *,
        database_url: URL,
        container_id: str,
        server_identifier: str,
        backup_root: Path,
        run_id: str,
        compose_file: Path,
        project_name: str,
        expected_port: int,
        service_kind: str = "compose",
    ) -> None:
        self.database_url = database_url
        self.container_id = container_id
        self.server_identifier = server_identifier
        if backup_root.is_symlink():
            raise TestDatabaseGuardError(
                "private recovery directory must not be a symlink"
            )
        self.backup_root = backup_root.resolve()
        self.backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup_metadata = self.backup_root.stat()
        if backup_metadata.st_uid != os.getuid() or not stat.S_ISDIR(
            backup_metadata.st_mode
        ):
            raise TestDatabaseGuardError(
                "private recovery directory has an invalid owner"
            )
        os.chmod(self.backup_root, 0o700)
        self.state_path = self.backup_root.parent / "owned-targets.json"
        self.state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        state_directory_metadata = self.state_path.parent.stat()
        if (
            self.state_path.parent.is_symlink()
            or state_directory_metadata.st_uid != os.getuid()
            or not stat.S_ISDIR(state_directory_metadata.st_mode)
        ):
            raise TestDatabaseGuardError(
                "private database state directory has an invalid owner"
            )
        os.chmod(self.state_path.parent, 0o700)
        self.compose_file = compose_file.resolve()
        self.project_name = project_name
        self.expected_port = expected_port
        self.service_kind = service_kind
        self.run_id = run_id
        self._ensure_state()
        self._archive_sequence = 0

    @classmethod
    def from_environment(cls) -> DatabaseLifecycle:
        database_url = require_test_database_url()
        container_id = os.environ.get("EMAIL_SUPPORT_TEST_CONTAINER_ID")
        server_identifier = os.environ.get("EMAIL_SUPPORT_TEST_SERVER_IDENTIFIER")
        backup_root_value = os.environ.get("EMAIL_SUPPORT_TEST_BACKUP_DIR")
        run_id = os.environ.get("EMAIL_SUPPORT_TEST_RUN_ID")
        compose_file = os.environ.get("EMAIL_SUPPORT_TEST_COMPOSE_FILE")
        project_name = os.environ.get("EMAIL_SUPPORT_TEST_PROJECT_NAME")
        port_value = os.environ.get("EMAIL_SUPPORT_TEST_PORT")
        service_kind = os.environ.get("EMAIL_SUPPORT_TEST_SERVICE_KIND", "compose")
        if (
            not container_id
            or not server_identifier
            or not backup_root_value
            or not run_id
            or not compose_file
            or not project_name
            or not port_value
            or service_kind not in {"compose", "github-actions"}
        ):
            raise TestDatabaseGuardError(
                "verified test database lifecycle settings are required"
            )
        if not re.fullmatch(r"[a-f0-9]{8}", run_id):
            raise TestDatabaseGuardError("test database run identifier is invalid")
        try:
            expected_port = int(port_value)
        except ValueError as error:
            raise TestDatabaseGuardError("test database port is invalid") from error
        if expected_port != 55432:
            raise TestDatabaseGuardError(
                "test database port is not the configured loopback port"
            )
        return cls(
            database_url=database_url,
            container_id=container_id,
            server_identifier=server_identifier,
            backup_root=Path(backup_root_value),
            run_id=run_id,
            compose_file=Path(compose_file),
            project_name=project_name,
            expected_port=expected_port,
            service_kind=service_kind,
        )

    def _ensure_state(self) -> None:
        if self.state_path.is_symlink() or (
            self.state_path.exists() and not self.state_path.is_file()
        ):
            raise TestDatabaseGuardError(
                "private database ownership state must be a regular file"
            )
        if not self.state_path.exists():
            self._write_state({"counter": 0, "targets": []})
        metadata = self.state_path.stat()
        if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
            raise TestDatabaseGuardError(
                "private database ownership state is not private"
            )
        self._read_state()

    def _read_state(self) -> dict[str, object]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise TestDatabaseGuardError(
                "private database ownership state is unreadable"
            ) from error
        if (
            not isinstance(value, dict)
            or not isinstance(value.get("counter"), int)
            or not isinstance(value.get("targets"), list)
            or any(not isinstance(name, str) for name in value["targets"])
        ):
            raise TestDatabaseGuardError("private database ownership state is invalid")
        return value

    def _write_state(self, state: dict[str, object]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.state_path.with_suffix(".json.tmp")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as state_file:
            json.dump(state, state_file, sort_keys=True)
            state_file.write("\n")
            state_file.flush()
            os.fsync(state_file.fileno())
        os.replace(temporary, self.state_path)
        os.chmod(self.state_path, 0o600)

    def _owned_targets(self) -> list[str]:
        state = self._read_state()
        targets = state["targets"]
        if not isinstance(targets, list):
            raise TestDatabaseGuardError("private database ownership state is invalid")
        for target in targets:
            if not isinstance(target, str) or not TEST_DATABASE_NAME.fullmatch(target):
                raise TestDatabaseGuardError(
                    "private database ownership allowlist is invalid"
                )
        return list(targets)

    def _set_targets(self, targets: list[str], *, counter: int | None = None) -> None:
        state = self._read_state()
        current_counter = state["counter"]
        if not isinstance(current_counter, int):
            raise TestDatabaseGuardError("private database ownership state is invalid")
        self._write_state(
            {
                "counter": current_counter if counter is None else counter,
                "targets": targets,
            }
        )

    def _database_url(self, database: str) -> URL:
        return self.database_url.set(database=database)

    def _verify_identity(self, database: str) -> DatabaseIdentity:
        if database != CONTROL_DATABASE and database not in self._owned_targets():
            raise TestDatabaseGuardError(
                "database is not in the generated test target allowlist"
            )
        if self.service_kind == "github-actions":
            verified_container_id = verify_github_actions_container(
                container_id=self.container_id,
                compose_file=self.compose_file,
                project_name=self.project_name,
                expected_port=self.expected_port,
            )
        else:
            verified_container_id = verify_owned_container(
                container_id=self.container_id,
                compose_file=self.compose_file,
                project_name=self.project_name,
                expected_port=self.expected_port,
            )
        if verified_container_id != self.container_id:
            raise TestDatabaseGuardError("test PostgreSQL container identity changed")
        actual_database, actual_role, server_identifier = _server_identity(
            self._database_url(database)
        )
        actual = DatabaseIdentity(
            database=actual_database,
            role=actual_role,
            container_id=self.container_id,
            server_identifier=server_identifier,
        )
        expected = DatabaseIdentity(
            database=database,
            role=TEST_ROLE,
            container_id=self.container_id,
            server_identifier=self.server_identifier,
        )
        validate_target_identity(actual, expected)
        return actual

    def _run_container_utility(self, args: Sequence[str]) -> None:
        result = _run(["docker", "exec", self.container_id, *args])
        if result.returncode != 0:
            raise TestDatabaseGuardError("owned PostgreSQL utility failed")

    def _database_exists(self, database: str) -> bool:
        self._verify_identity(CONTROL_DATABASE)
        try:
            with psycopg.connect(
                _url_for_database(self.database_url, CONTROL_DATABASE).render_as_string(
                    hide_password=False
                ),
                connect_timeout=5,
            ) as connection:
                row = connection.execute(
                    "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = %s)",
                    (database,),
                ).fetchone()
        except psycopg.Error as error:
            raise TestDatabaseGuardError(
                "test database inventory query failed"
            ) from error
        return row is not None and row[0] is True

    def _archive_path(self, database: str, purpose: str) -> Path:
        self._archive_sequence += 1
        safe_purpose = re.sub(r"[^a-z0-9]+", "_", purpose.lower()).strip("_")[:28]
        return self.backup_root / (
            f"{self.run_id}-{self._archive_sequence:05d}-{database}-{safe_purpose}.dump"
        )

    def backup_database(self, database: str, purpose: str) -> Path:
        self._verify_identity(database)
        archive_path = self._archive_path(database, purpose)
        descriptor = os.open(archive_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as archive_file:
                result = subprocess.run(
                    [
                        "docker",
                        "exec",
                        self.container_id,
                        "pg_dump",
                        "--format=custom",
                        "--no-owner",
                        "--no-privileges",
                        "--username",
                        TEST_ROLE,
                        "--dbname",
                        database,
                    ],
                    check=False,
                    stdout=archive_file,
                    stderr=subprocess.PIPE,
                )
            if result.returncode != 0:
                raise TestDatabaseGuardError("pg_dump failed; mutation was stopped")
            self._verify_archive(archive_path)
        except OSError as error:
            raise TestDatabaseGuardError(
                "private database backup could not be verified"
            ) from error
        return archive_path

    def _verify_archive(self, archive_path: Path) -> Path:
        if archive_path.is_symlink():
            raise TestDatabaseGuardError("database archive must not be a symlink")
        try:
            resolved_path = archive_path.resolve(strict=True)
            metadata = resolved_path.stat()
        except OSError as error:
            raise TestDatabaseGuardError("database archive is unavailable") from error
        if (
            resolved_path.parent != self.backup_root
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or metadata.st_mode & 0o077
            or metadata.st_size == 0
        ):
            raise TestDatabaseGuardError(
                "database archive is not an owned private recovery file"
            )
        with resolved_path.open("rb") as archive_file:
            verification = subprocess.run(
                [
                    "docker",
                    "exec",
                    "--interactive",
                    self.container_id,
                    "pg_restore",
                    "--list",
                ],
                check=False,
                stdin=archive_file,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        if verification.returncode != 0:
            raise TestDatabaseGuardError(
                "pg_restore list verification failed; mutation was stopped"
            )
        return resolved_path

    def restore_target(self, archive_path: Path, scenario: str) -> str:
        """Restore one verified private archive into a fresh guarded target."""
        archive = self._verify_archive(archive_path)
        database = self.create_target(scenario)

        def restore_database() -> None:
            self._verify_identity(database)
            with archive.open("rb") as archive_file:
                restored = subprocess.run(
                    [
                        "docker",
                        "exec",
                        "--interactive",
                        self.container_id,
                        "pg_restore",
                        "--exit-on-error",
                        "--single-transaction",
                        "--no-owner",
                        "--no-privileges",
                        "--username",
                        TEST_ROLE,
                        "--dbname",
                        database,
                    ],
                    check=False,
                    stdin=archive_file,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
            if restored.returncode != 0:
                raise TestDatabaseGuardError(
                    "verified archive could not be restored into its guarded target"
                )
            self._verify_identity(database)

        run_guarded_mutation(
            backup=lambda: self.backup_database(database, "before-restore"),
            mutation=restore_database,
            recovery_path=self.backup_root,
        )
        return database

    def create_target(self, scenario: str) -> str:
        state = self._read_state()
        counter = state["counter"]
        if not isinstance(counter, int):
            raise TestDatabaseGuardError("private database ownership state is invalid")
        counter += 1
        scenario_slug = re.sub(r"[^a-z0-9]+", "_", scenario.lower()).strip("_")[:24]
        if not scenario_slug:
            scenario_slug = "scenario"
        database = f"{TEST_DATABASE_PREFIX}{self.run_id}_{counter:05d}_{scenario_slug}"
        if not TEST_DATABASE_NAME.fullmatch(database):
            raise TestDatabaseGuardError("generated test database name is invalid")
        targets = self._owned_targets()
        if database in targets:
            raise TestDatabaseGuardError("generated test database name already exists")
        self._write_state({"counter": counter, "targets": [*targets, database]})

        def create_database() -> None:
            self._verify_identity(CONTROL_DATABASE)
            self._run_container_utility(
                [
                    "createdb",
                    "--username",
                    TEST_ROLE,
                    "--maintenance-db",
                    CONTROL_DATABASE,
                    database,
                ]
            )

        run_guarded_mutation(
            backup=lambda: self.backup_database(CONTROL_DATABASE, "before-create"),
            mutation=create_database,
            recovery_path=self.backup_root,
        )
        self.backup_database(database, "before-migration")
        return database

    def target_url(self, database: str) -> str:
        if database not in self._owned_targets():
            raise TestDatabaseGuardError(
                "database is not in the generated test target allowlist"
            )
        return self._database_url(database).render_as_string(hide_password=False)

    def drop_target(self, database: str) -> None:
        targets = self._owned_targets()
        if database not in targets:
            raise TestDatabaseGuardError(
                "database is not in the generated test target allowlist"
            )
        if not self._database_exists(database):
            self._set_targets([target for target in targets if target != database])
            return

        def backup_databases() -> None:
            self.backup_database(database, "before-drop")
            self.backup_database(CONTROL_DATABASE, "before-drop")

        def drop_database() -> None:
            self._verify_identity(CONTROL_DATABASE)
            self._run_container_utility(
                [
                    "dropdb",
                    "--if-exists",
                    "--username",
                    TEST_ROLE,
                    "--maintenance-db",
                    CONTROL_DATABASE,
                    database,
                ]
            )

        run_guarded_mutation(
            backup=backup_databases,
            mutation=drop_database,
            recovery_path=self.backup_root,
        )
        self._set_targets([target for target in targets if target != database])

    def recover_owned_targets(self) -> None:
        for database in list(self._owned_targets()):
            if self._database_exists(database):
                self.drop_target(database)
            else:
                targets = self._owned_targets()
                self._set_targets([target for target in targets if target != database])

    def shutdown_cleanup(self) -> None:
        self.recover_owned_targets()
        self.backup_database(CONTROL_DATABASE, "before-shutdown")

    def remove_current_run_archives(self) -> None:
        if self._owned_targets():
            raise TestDatabaseGuardError(
                "cannot remove recovery archives while targets remain"
            )
        for archive_path in self.backup_root.glob(f"{self.run_id}-*.dump"):
            archive_path.unlink()


def run_migrations(database_url: str, revision: str = "head") -> None:
    environment = os.environ.copy()
    environment[ALEMBIC_DATABASE_URL] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "upgrade", revision],
        cwd=BACKEND_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        safe_url = make_url(database_url).render_as_string(hide_password=True)
        details = f"{result.stdout}{result.stderr}".replace(database_url, safe_url)
        sys.stderr.write(details)
        raise TestDatabaseGuardError("Alembic migration failed")


def check_migration_drift(database_url: str) -> None:
    environment = os.environ.copy()
    environment[ALEMBIC_DATABASE_URL] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "alembic.ini", "check"],
        cwd=BACKEND_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        safe_url = make_url(database_url).render_as_string(hide_password=True)
        details = f"{result.stdout}{result.stderr}".replace(database_url, safe_url)
        sys.stderr.write(details)
        raise TestDatabaseGuardError("Alembic metadata drift detected")


def _lifecycle() -> DatabaseLifecycle:
    return DatabaseLifecycle.from_environment()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify-service")
    verify.add_argument("--container-id", required=True)
    verify.add_argument("--compose-file", type=Path, required=True)
    verify.add_argument("--project-name", required=True)
    verify.add_argument("--port", type=int, required=True)
    verify.add_argument(
        "--service-kind", choices=("compose", "github-actions"), default="compose"
    )
    stop = commands.add_parser("stop-owned")
    stop.add_argument("--container-id", required=True)
    stop.add_argument("--compose-file", type=Path, required=True)
    stop.add_argument("--project-name", required=True)
    stop.add_argument("--port", type=int, required=True)
    commands.add_parser("shutdown-cleanup")
    commands.add_parser("recover-owned-targets")
    commands.add_parser("finish-success")
    args = parser.parse_args()

    try:
        if args.command == "verify-service":
            server_identifier = verify_service(
                container_id=args.container_id,
                compose_file=args.compose_file,
                project_name=args.project_name,
                expected_port=args.port,
                service_kind=args.service_kind,
            )
            print(server_identifier)
        elif args.command == "stop-owned":
            verify_owned_container(
                container_id=args.container_id,
                compose_file=args.compose_file,
                project_name=args.project_name,
                expected_port=args.port,
            )
            stopped = _run(["docker", "stop", args.container_id])
            if stopped.returncode != 0:
                raise TestDatabaseGuardError(
                    "verified PostgreSQL test service did not stop"
                )
        elif args.command == "recover-owned-targets":
            _lifecycle().recover_owned_targets()
        elif args.command == "shutdown-cleanup":
            _lifecycle().shutdown_cleanup()
        elif args.command == "finish-success":
            lifecycle = _lifecycle()
            lifecycle.recover_owned_targets()
            lifecycle.remove_current_run_archives()
        return 0
    except TestDatabaseGuardError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
