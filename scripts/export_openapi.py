"""Export deterministic OpenAPI descriptions without starting a server."""

import json
from pathlib import Path

from apps.api.main import app as public_app
from apps.guardian.main import app as guardian_app
from apps.mcp_server.main import app as mcp_app


def main() -> None:
    output = Path("openapi/generated")
    output.mkdir(parents=True, exist_ok=True)
    documents = {
        "xyena-public-v1.json": public_app.openapi(),
        "guardian-internal-v1.json": guardian_app.openapi(),
        "mcp-control-internal-v1.json": mcp_app.openapi(),
    }
    for filename, document in documents.items():
        (output / filename).write_text(
            json.dumps(document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
