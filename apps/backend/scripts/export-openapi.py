"""Write the application OpenAPI document without starting a server."""

import json
from pathlib import Path

from email_support.main import app


def main() -> None:
    """Export a stable, sorted OpenAPI document beside this project."""
    output_path = Path(__file__).resolve().parents[1] / "openapi.json"
    document = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    output_path.write_text(document, encoding="utf-8")


if __name__ == "__main__":
    main()
