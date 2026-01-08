from __future__ import annotations

import os
from collections.abc import Mapping

from cryptography.fernet import Fernet, InvalidToken

ENCRYPTION_PREFIX = "enc:"
SENSITIVE_KEYWORDS = ("PASSWORD", "SECRET", "TOKEN", "API_KEY", "KEY")


def is_sensitive_env_key(key: str) -> bool:
    key_upper = (key or "").upper()
    return any(keyword in key_upper for keyword in SENSITIVE_KEYWORDS)


def _get_fernet() -> Fernet:
    key = os.getenv("MCP_ENCRYPTION_KEY")
    if not key:
        raise ValueError("MCP_ENCRYPTION_KEY is not set")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Invalid MCP_ENCRYPTION_KEY") from exc


def encrypt_env_values(env: Mapping[str, object]) -> dict[str, object]:
    """Encrypt sensitive env values in-place, leaving non-sensitive values untouched."""
    encrypted: dict[str, object] = dict(env)
    needs_encryption = any(is_sensitive_env_key(k) and bool(v) for k, v in encrypted.items())
    if not needs_encryption:
        return encrypted

    fernet = _get_fernet()
    for key, value in list(encrypted.items()):
        if not is_sensitive_env_key(key):
            continue
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            raise ValueError(f"env.{key} must be a string")
        token = fernet.encrypt(value.encode("utf-8")).decode("utf-8")
        encrypted[key] = f"{ENCRYPTION_PREFIX}{token}"
    return encrypted


def decrypt_env_values(env: Mapping[str, object]) -> dict[str, str]:
    decrypted: dict[str, str] = {}
    fernet: Fernet | None = None

    for key, value in env.items():
        if value is None:
            continue
        if not isinstance(value, str):
            raise ValueError(f"env.{key} must be a string")
        if value.startswith(ENCRYPTION_PREFIX):
            if fernet is None:
                fernet = _get_fernet()
            token = value.removeprefix(ENCRYPTION_PREFIX)
            try:
                decrypted[key] = fernet.decrypt(token.encode("utf-8")).decode("utf-8")
            except InvalidToken as exc:
                raise ValueError("Failed to decrypt env value") from exc
        else:
            decrypted[key] = value
    return decrypted


def build_env_status(config_template: Mapping[str, object] | None, config: Mapping[str, object] | None) -> dict:
    template = config_template or {}
    cfg = config or {}

    required = template.get("env_required") or []
    optional = template.get("env_optional") or []
    env_keys: list[str] = []
    if isinstance(required, list):
        env_keys.extend([k for k in required if isinstance(k, str)])
    if isinstance(optional, list):
        env_keys.extend([k for k in optional if isinstance(k, str)])

    env = cfg.get("env") if isinstance(cfg, Mapping) else None
    env_map: Mapping[str, object] = env if isinstance(env, Mapping) else {}
    for key in env_map.keys():
        if isinstance(key, str) and key not in env_keys:
            env_keys.append(key)

    status: dict[str, dict[str, bool]] = {}
    for key in env_keys:
        value = env_map.get(key)
        is_set = value is not None and value != ""
        status[key] = {"is_sensitive": is_sensitive_env_key(key), "is_set": bool(is_set)}
    return status
