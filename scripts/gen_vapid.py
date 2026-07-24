"""
scripts/gen_vapid.py — generate a VAPID key pair for Web Push (Phase 2).

VAPID keys are how a push service verifies that notifications really come from
YOUR server. You generate them ONCE and keep the same pair forever (changing
them invalidates every existing subscription).

Run from the project root:
    python scripts/gen_vapid.py

Then copy the two printed lines into your .env file (and later into Render's
environment variables).
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(data: bytes) -> str:
    """URL-safe base64 without padding — the format the Web Push spec uses."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def main() -> None:
    # VAPID uses an elliptic-curve (P-256) key pair.
    private_key = ec.generate_private_key(ec.SECP256R1())

    # --- Private key: raw 32-byte scalar, base64url-encoded ---
    private_value = private_key.private_numbers().private_value
    private_bytes = private_value.to_bytes(32, "big")
    private_b64 = _b64url(private_bytes)

    # --- Public key: uncompressed point (65 bytes), base64url-encoded ---
    public_bytes = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    public_b64 = _b64url(public_bytes)

    print("\n✅ VAPID key pair generated. Add these to your .env file:\n")
    print(f"VAPID_PUBLIC_KEY={public_b64}")
    print(f"VAPID_PRIVATE_KEY={private_b64}")
    print("\n(Keep VAPID_SUBJECT as your mailto: address. Never share the private key.)\n")


if __name__ == "__main__":
    main()
