import os


class SecretResolutionError(Exception):
    pass


class SecretResolver:
    """Resolve secret references without persisting plaintext connector credentials."""

    def resolve(self, reference: str | None) -> str | None:
        if reference is None:
            return None
        if reference.startswith("env://"):
            name = reference.removeprefix("env://")
            value = os.getenv(name)
            if not value:
                raise SecretResolutionError(f"Secret environment reference {name!r} is unavailable")
            return value
        raise SecretResolutionError("Only env:// references are enabled; configure a cloud resolver")

