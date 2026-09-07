"""Authentication and credential handling.

Design notes
------------
* API keys are high-entropy random secrets. They are stored as a SHA-256 digest
  and compared in constant time. The plaintext is shown exactly once, at
  creation, and is never stored or logged.
* Passwords are low-entropy human input, so they get a memory-hard KDF
  (``hashlib.scrypt``) with a per-hash random salt.
* JWT is used only for the admin dashboard session cookie, not for the
  machine-to-machine API, which uses API keys.

stdlib only: no passlib/bcrypt version traps in the deployment image.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass

API_KEY_PREFIX = "ahk"
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32


# --------------------------------------------------------------------- keys
@dataclass(frozen=True)
class GeneratedApiKey:
    key_id: str
    secret: str
    plaintext: str
    hashed: str


def generate_api_key() -> GeneratedApiKey:
    key_id = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    plaintext = f"{API_KEY_PREFIX}_{key_id}.{secret}"
    return GeneratedApiKey(
        key_id=key_id, secret=secret, plaintext=plaintext, hashed=hash_api_key(plaintext)
    )


def hash_api_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def verify_api_key(plaintext: str, hashed: str) -> bool:
    return hmac.compare_digest(hash_api_key(plaintext), hashed or "")


def parse_api_key(plaintext: str) -> str | None:
    """Return the key_id portion, or None if the key is not well formed."""
    if not plaintext or not plaintext.startswith(f"{API_KEY_PREFIX}_"):
        return None
    body = plaintext[len(API_KEY_PREFIX) + 1 :]
    key_id, sep, secret = body.partition(".")
    if not sep or not key_id or not secret:
        return None
    return key_id


# ---------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, n, r, p, salt_b64, dk_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt_b64),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(base64.b64decode(dk_b64)),
        )
        return hmac.compare_digest(dk, base64.b64decode(dk_b64))
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------- JWT
def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64u_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def create_session_token(subject: str, secret: str, ttl_minutes: int, role: str = "admin") -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"sub": subject, "role": role, "iat": now, "exp": now + ttl_minutes * 60}
    signing_input = f"{_b64u(json.dumps(header, separators=(',', ':')).encode())}." f"{_b64u(json.dumps(payload, separators=(',', ':')).encode())}"
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64u(sig)}"


def verify_session_token(token: str, secret: str) -> dict | None:
    try:
        head_b64, payload_b64, sig_b64 = token.split(".")
    except (ValueError, AttributeError):
        return None
    signing_input = f"{head_b64}.{payload_b64}"
    expected = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(expected, _b64u_decode(sig_b64)):
            return None
        payload = json.loads(_b64u_decode(payload_b64))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload
