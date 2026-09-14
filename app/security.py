"""Minimal auth helpers: password hashing + signed session tokens.

Kept dependency-free (stdlib only) so the admin-tab login works without extra
packages. Production would swap this for OAuth/SSO (noted as future work).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Optional

from app.config import settings

_PBKDF2_ROUNDS = 100_000
_TOKEN_TTL_SECONDS = 24 * 60 * 60  # 1 day


def hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ROUNDS).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _algo, salt, digest = encoded.split("$", 2)
        check = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _PBKDF2_ROUNDS).hex()
        return hmac.compare_digest(check, digest)
    except Exception:
        return False


def create_token(email: str) -> str:
    exp = int(time.time()) + _TOKEN_TTL_SECONDS
    payload = f"{email}|{exp}"
    sig = hmac.new(settings.secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()


def verify_token(token: str) -> Optional[str]:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        email, exp, sig = raw.rsplit("|", 2)
        if int(exp) < time.time():
            return None
        expected = hmac.new(settings.secret_key.encode(), f"{email}|{exp}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            return None
        return email
    except Exception:
        return None
