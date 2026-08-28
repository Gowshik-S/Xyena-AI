"""Configure a model provider in the protected deployment environment."""

from __future__ import annotations

import argparse
import getpass
import os
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".env"

PROVIDERS = {
    "openai": {
        "key_name": "XYENA_OPENAI_API_KEY",
        "default_model": "gpt-5.6-terra",
        "extra": {},
    },
    "command_code": {
        "key_name": "XYENA_COMMAND_CODE_API_KEY",
        "default_model": "deepseek/deepseek-v4-flash",
        "extra": {
            "XYENA_COMMAND_CODE_BASE_URL": "https://api.commandcode.ai/provider/v1",
            "XYENA_COMMAND_CODE_ZDR": "true",
        },
    },
    "nvidia_nim": {
        "key_name": "XYENA_NVIDIA_NIM_API_KEY",
        "default_model": "openai/gpt-oss-20b",
        "extra": {
            "XYENA_NVIDIA_NIM_BASE_URL": "https://integrate.api.nvidia.com/v1",
        },
    },
}


def replace_values(contents: str, updates: dict[str, str]) -> str:
    remaining = dict(updates)
    output: list[str] = []
    for line in contents.splitlines():
        name, separator, _ = line.partition("=")
        if separator and name in remaining:
            output.append(f"{name}={remaining.pop(name)}")
        else:
            output.append(line)
    output.extend(f"{name}={value}" for name, value in remaining.items())
    return "\n".join(output) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provider", choices=PROVIDERS)
    parser.add_argument("--model", help="provider model identifier")
    parser.add_argument(
        "--key-count",
        type=int,
        default=1,
        help="number of keys to prompt for; multiple keys are supported by nvidia_nim",
    )
    args = parser.parse_args()

    if not ENV_FILE.exists():
        raise SystemExit(f"{ENV_FILE} does not exist; run generate_env.py first")

    if args.key_count < 1:
        raise SystemExit("--key-count must be at least 1")
    if args.provider != "nvidia_nim" and args.key_count != 1:
        raise SystemExit("multiple keys are currently supported only for nvidia_nim")

    provider = PROVIDERS[args.provider]
    api_keys: list[str] = []
    for position in range(1, args.key_count + 1):
        api_key = getpass.getpass(
            f"Enter {args.provider} API key {position}/{args.key_count}: "
        ).strip()
        if not api_key:
            raise SystemExit("API key was empty; no changes made")
        if "\n" in api_key or "\r" in api_key or "," in api_key:
            raise SystemExit("API key contains an invalid delimiter; no changes made")
        api_keys.append(api_key)

    api_keys = list(dict.fromkeys(api_keys))

    updates = {
        "XYENA_MODEL_PROVIDER": args.provider,
        "XYENA_OPENAI_MODEL": args.model or provider["default_model"],
        provider["key_name"]: api_keys[0],
        **provider["extra"],
    }
    if args.provider == "nvidia_nim":
        updates["XYENA_NVIDIA_NIM_API_KEYS"] = ",".join(api_keys)
    updated = replace_values(ENV_FILE.read_text(encoding="utf-8"), updates)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=ENV_FILE.parent,
        prefix=".env.",
        delete=False,
    ) as temporary:
        temporary.write(updated)
        temporary_path = Path(temporary.name)
    try:
        temporary_path.chmod(0o600)
        os.replace(temporary_path, ENV_FILE)
        ENV_FILE.chmod(0o600)
    finally:
        temporary_path.unlink(missing_ok=True)

    print(
        f"Configured {args.provider} with model {updates['XYENA_OPENAI_MODEL']} and "
        f"{len(api_keys)} key(s); keys were not printed."
    )


if __name__ == "__main__":
    main()
