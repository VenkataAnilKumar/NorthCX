"""Signed built-in templates (WP22.9): an Ed25519 signature over each built-in template's content hash.

The public key and the signatures ship with the code (`template_library/`). A built-in whose content no longer matches its signature is
shown as tampered and cannot be installed. Templates from other directories and organization templates say where they came from instead.
"""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

KEY_FILE = "signing_key.pub"
SIGNATURES_FILE = "SIGNATURES.json"


def content_hash(data: Any) -> str:
    """SHA-256 of the template as a canonical JSON document, so formatting and key order never matter."""
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()).hexdigest()


def generate_key() -> tuple[bytes, bytes]:
    k = Ed25519PrivateKey.generate()
    return (k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()),
            k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))


def sign(private_pem: bytes, template_id: str, version: str, digest: str) -> str:
    key = serialization.load_pem_private_key(private_pem, password=None)
    assert isinstance(key, Ed25519PrivateKey)
    return base64.b64encode(key.sign(_message(template_id, version, digest))).decode()


def _message(template_id: str, version: str, digest: str) -> bytes:
    return f"northcx-template\n{template_id}\n{version}\n{digest}".encode()


class Verifier:
    """Checks built-in templates against the shipped public key and signature list."""

    def __init__(self, library: Path):
        self.signatures: dict[str, dict[str, str]] = {}
        self.key: Ed25519PublicKey | None = None
        try:
            pub = serialization.load_pem_public_key((library / KEY_FILE).read_bytes())
            if isinstance(pub, Ed25519PublicKey):
                self.key = pub
            self.signatures = json.loads((library / SIGNATURES_FILE).read_text()).get("templates", {})
        except (OSError, ValueError):
            pass

    @property
    def fingerprint(self) -> str | None:
        if self.key is None:
            return None
        raw = self.key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return hashlib.sha256(raw).hexdigest()[:16]

    def check(self, template_id: str, version: str, digest: str) -> dict[str, Any]:
        base = {"source": "built-in", "keyFingerprint": self.fingerprint, "contentHash": digest}
        sig = self.signatures.get(template_id)
        if self.key is None or sig is None:
            return {**base, "signed": False, "verified": False, "status": "unsigned"}
        if sig.get("hash") != digest or sig.get("version") != version:
            return {**base, "signed": True, "verified": False, "status": "changed since it was signed"}
        try:
            self.key.verify(base64.b64decode(sig["signature"]), _message(template_id, version, digest))
        except (InvalidSignature, ValueError, KeyError):
            return {**base, "signed": True, "verified": False, "status": "signature does not match"}
        return {**base, "signed": True, "verified": True, "status": "verified"}
