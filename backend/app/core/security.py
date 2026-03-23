from __future__ import annotations

import hashlib
import hmac
import secrets
from base64 import urlsafe_b64encode
import re


def validate_password_strength(password: str, *, min_length: int = 12) -> None:
    if len(password) < min_length:
        raise ValueError(f"密码长度至少需要 {min_length} 位。")
    if password.lower() == password:
        raise ValueError("密码必须至少包含一个大写字母。")
    if password.upper() == password:
        raise ValueError("密码必须至少包含一个小写字母。")
    if not re.search(r"\d", password):
        raise ValueError("密码必须至少包含一个数字。")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("密码必须至少包含一个特殊字符。")


def is_default_weak_password(password: str) -> bool:
    return password in {"admin123", "123456", "password", "admin", "root", "qwerty"}


def hash_password(password: str, salt: str | None = None) -> str:
    salt_value = salt or secrets.token_hex(16)
    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_value.encode("utf-8"),
        120_000,
    )
    return f"{salt_value}${derived_key.hex()}"


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        salt, expected = hashed_password.split("$", 1)
    except ValueError:
        return False
    candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, f"{salt}${expected}")


def generate_access_token() -> str:
    return urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
