"""
common.crypto
=============
Shared RSA-SHA256 cryptographic primitives used by both
sentinel-conductor (signing) and sentinel-target (verification).

Having these in ``common`` means neither component needs to import
from the other's package.
"""

import base64
import json
import pathlib
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey

from common.exceptions import SignatureVerificationFailed


# ---------------------------------------------------------------------------
# Key I/O
# ---------------------------------------------------------------------------

def load_private_key(path: str | pathlib.Path) -> RSAPrivateKey:
    """Load a PEM-encoded RSA private key from disk."""
    pem = pathlib.Path(path).read_bytes()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, RSAPrivateKey):
        raise ValueError(f"Expected RSA private key, got {type(key).__name__}")
    return key


def load_public_key(path: str | pathlib.Path) -> RSAPublicKey:
    """Load a PEM-encoded RSA public key from disk."""
    pem = pathlib.Path(path).read_bytes()
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, RSAPublicKey):
        raise ValueError(f"Expected RSA public key, got {type(key).__name__}")
    return key


# ---------------------------------------------------------------------------
# Canonical serialisation
# ---------------------------------------------------------------------------

def canonical_bytes(data: dict[str, Any]) -> bytes:
    """
    Produce a stable, deterministic UTF-8 byte string from a dict.

    Rules:
    - Keys sorted recursively (``sort_keys=True``).
    - No extra whitespace (``separators=(',', ':')``)
    - Encoded as UTF-8.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")


def signable_material(payload_dict: dict[str, Any]) -> bytes:
    """
    Extract and serialise the fields covered by the RSA signature.

    Signed material = execution + context + security.timestamp.

    The ``security.signature`` field itself is excluded (it's circular).
    The timestamp is included to enable replay-attack protection.
    """
    material = {
        "execution": payload_dict["execution"],
        "context": payload_dict["context"],
        "timestamp": payload_dict["security"]["timestamp"],
    }
    return canonical_bytes(material)


# ---------------------------------------------------------------------------
# Sign
# ---------------------------------------------------------------------------

def sign_payload(payload_dict: dict[str, Any], private_key: RSAPrivateKey) -> str:
    """
    RSA-SHA256 sign the canonical material of an execution payload.

    Args:
        payload_dict:  Full payload dict. ``security.signature`` may be
                       an empty string — it is excluded from signing.
        private_key:   Conductor's RSA private key.

    Returns:
        Base64-encoded signature string (ASCII-safe).
    """
    raw = private_key.sign(
        signable_material(payload_dict),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(raw).decode("ascii")


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------

def verify_payload_signature(
    payload_dict: dict[str, Any],
    public_key: RSAPublicKey,
) -> None:
    """
    Verify the RSA-SHA256 signature embedded in a payload dict.

    Args:
        payload_dict:  Full payload dict including the security block.
        public_key:    Conductor's RSA public key.

    Raises:
        common.exceptions.SignatureVerificationFailed: on any failure.
    """
    try:
        signature_b64 = payload_dict["security"]["signature"]
        raw_signature = base64.b64decode(signature_b64)
    except (KeyError, ValueError) as exc:
        raise SignatureVerificationFailed(
            "Payload is missing or has a malformed security.signature field."
        ) from exc

    try:
        public_key.verify(
            raw_signature,
            signable_material(payload_dict),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except Exception as exc:
        raise SignatureVerificationFailed(
            f"RSA-SHA256 signature verification failed: {exc}"
        ) from exc
