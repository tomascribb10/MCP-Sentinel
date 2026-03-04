"""
sentinel_conductor.crypto
==========================
Conductor-specific crypto: signing helpers, key generation and persistence.

Verification primitives live in ``common.crypto`` so the agent can use
them without importing from this package.
"""

import pathlib

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

# Re-export shared primitives so callers only need one import
from common.crypto import (  # noqa: F401
    load_private_key,
    load_public_key,
    sign_payload,
    verify_payload_signature,
)


def public_key_pem(private_key: RSAPrivateKey) -> bytes:
    """Return the PEM-encoded public key derived from a private key."""
    return private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def generate_rsa_keypair(key_bits: int = 4096) -> tuple[RSAPrivateKey, RSAPublicKey]:
    """Generate a new RSA key pair. Returns (private_key, public_key)."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_bits,
    )
    return private_key, private_key.public_key()


def save_keypair(
    private_key: RSAPrivateKey,
    private_path: str | pathlib.Path,
    public_path: str | pathlib.Path,
) -> None:
    """Write a key pair to PEM files (private key unencrypted)."""
    pathlib.Path(private_path).write_bytes(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    pathlib.Path(public_path).write_bytes(
        private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
