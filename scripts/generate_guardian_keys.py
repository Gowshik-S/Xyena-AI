"""Generate an Ed25519 Guardian key pair; prints environment-safe values to stdout."""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> None:
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    private_env = private_pem.replace("\n", "\\n")
    public_env = public_pem.replace("\n", "\\n")
    print(f"XYENA_GUARDIAN_SIGNING_KEY={private_env}")
    print(f"XYENA_GUARDIAN_VERIFY_KEY={public_env}")


if __name__ == "__main__":
    main()
