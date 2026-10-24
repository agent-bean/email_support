import subprocess
import sys
from pathlib import Path

from email_support.main import app


def test_openapi_describes_health_response() -> None:
    schema = app.openapi()
    operation = schema["paths"]["/api/health"]["get"]
    health_response = schema["components"]["schemas"]["HealthResponse"]
    health_status = schema["components"]["schemas"]["HealthStatus"]

    assert operation["operationId"] == "get_health"
    assert health_response["required"] == ["status"]
    assert health_response["properties"]["status"]["$ref"] == (
        "#/components/schemas/HealthStatus"
    )
    assert health_status["enum"] == ["ok"]
    assert health_response["additionalProperties"] is False


def test_offline_openapi_export_is_byte_stable() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    script = backend_dir / "scripts" / "export-openapi.py"
    snapshot = backend_dir / "openapi.json"

    subprocess.run([sys.executable, str(script)], cwd=backend_dir, check=True)
    first = snapshot.read_bytes()
    subprocess.run([sys.executable, str(script)], cwd=backend_dir, check=True)
    second = snapshot.read_bytes()

    assert first == second
    assert first.endswith(b"\n")
