"""Export deterministic OpenAPI descriptions without starting a server."""

import json
from pathlib import Path

from apps.api.main import create_app


def main() -> None:
    output = Path("openapi/generated")
    output.mkdir(parents=True, exist_ok=True)
    document = create_app().openapi()
    (output / "xyena-public-v1.json").write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

