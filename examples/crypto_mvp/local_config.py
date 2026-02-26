"""
Local-only configuration and secret storage for Crypto MVP.

Design goals:
1) All sensitive values stay on local machine (outside git workspace).
2) Configuration is profile-based and easy to consume from scripts.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any


APP_NAME = "crypto_mvp"
ROOT_DIR: Path = Path.home() / ".vntrader" / APP_NAME
PROFILES_DIR: Path = ROOT_DIR / "profiles"


DEFAULT_SETTINGS: dict[str, Any] = {
    "network": {
        "proxy_host": "",
        "proxy_port": 0,
        "timeout": 15,
    },
    "binance": {
        "gateway_module": "vnpy_binance",
        "market": "spot",
        "server": "TESTNET",
        "kline_stream": True,
    },
    "qveris": {
        "base_url": "",
        "history_endpoint": "/v1/crypto/history",
        "latest_endpoint": "/v1/crypto/latest",
        "symbol_param": "symbol",
        "interval_param": "interval",
        "start_param": "start",
        "end_param": "end",
        "response_data_field": "data",
        "field_map": {
            "timestamp": "timestamp",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        },
    },
    "storage": {
        "sqlite_path": str((ROOT_DIR / "data" / "market_cache.sqlite3").resolve()),
    },
}


DEFAULT_SECRETS: dict[str, Any] = {
    "binance": {
        "spot": {"api_key": "", "api_secret": ""},
        "linear": {"api_key": "", "api_secret": ""},
        "inverse": {"api_key": "", "api_secret": ""},
    },
    "qveris": {
        "api_key": "",
        "api_secret": "",
    },
}


def ensure_dirs() -> None:
    """Create required local directories."""
    for path in [ROOT_DIR, PROFILES_DIR, ROOT_DIR / "data"]:
        path.mkdir(parents=True, exist_ok=True)


def _profile_paths(profile: str) -> tuple[Path, Path]:
    profile_name: str = profile.strip() or "default"
    settings_path: Path = PROFILES_DIR / f"{profile_name}.settings.json"
    secrets_path: Path = PROFILES_DIR / f"{profile_name}.secrets.json"
    return settings_path, secrets_path


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write_json(path: Path, data: dict[str, Any], *, secure_mode: bool) -> None:
    ensure_dirs()

    temp_path: Path = path.with_suffix(path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, sort_keys=True)

    os.replace(temp_path, path)

    # Keep local profile files readable/writable by current user only.
    if secure_mode:
        os.chmod(path, 0o600)


def _deep_merge(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = deepcopy(base)
    for key, value in updates.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


@dataclass
class LocalProfile:
    """Read/write local profile settings and secrets."""

    profile: str = "default"

    def load_settings(self) -> dict[str, Any]:
        """Load settings merged with defaults."""
        settings_path, _ = _profile_paths(self.profile)
        settings: dict[str, Any] = _read_json(settings_path)
        return _deep_merge(DEFAULT_SETTINGS, settings)

    def load_secrets(self) -> dict[str, Any]:
        """Load secrets merged with defaults."""
        _, secrets_path = _profile_paths(self.profile)
        secrets: dict[str, Any] = _read_json(secrets_path)
        return _deep_merge(DEFAULT_SECRETS, secrets)

    def save_settings(self, data: dict[str, Any]) -> None:
        """Save settings JSON."""
        settings_path, _ = _profile_paths(self.profile)
        _atomic_write_json(settings_path, data, secure_mode=True)

    def save_secrets(self, data: dict[str, Any]) -> None:
        """Save secrets JSON."""
        _, secrets_path = _profile_paths(self.profile)
        _atomic_write_json(secrets_path, data, secure_mode=True)

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Apply patch to settings and persist."""
        merged: dict[str, Any] = _deep_merge(self.load_settings(), patch)
        self.save_settings(merged)
        return merged

    def update_secrets(self, patch: dict[str, Any]) -> dict[str, Any]:
        """Apply patch to secrets and persist."""
        merged: dict[str, Any] = _deep_merge(self.load_secrets(), patch)
        self.save_secrets(merged)
        return merged

    def build_binance_gateway_setting(self, market: str) -> dict[str, str | int]:
        """Build vnpy_binance gateway setting from local profile."""
        settings: dict[str, Any] = self.load_settings()
        secrets: dict[str, Any] = self.load_secrets()

        network: dict[str, Any] = settings["network"]
        binance_cfg: dict[str, Any] = settings["binance"]
        market_secret: dict[str, str] = secrets["binance"][market]

        return {
            "API Key": market_secret.get("api_key", ""),
            "API Secret": market_secret.get("api_secret", ""),
            "Server": str(binance_cfg.get("server", "TESTNET")),
            "Kline Stream": "True" if bool(binance_cfg.get("kline_stream", True)) else "False",
            "Proxy Host": str(network.get("proxy_host", "")),
            "Proxy Port": int(network.get("proxy_port", 0)),
        }

    def build_qveris_auth_headers(self) -> dict[str, str]:
        """Build Qveris auth headers from local profile."""
        secrets: dict[str, Any] = self.load_secrets()
        qveris_secret: dict[str, str] = secrets.get("qveris", {})

        api_key: str = qveris_secret.get("api_key", "").strip()
        api_secret: str = qveris_secret.get("api_secret", "").strip()

        headers: dict[str, str] = {}
        if api_key:
            headers["X-API-KEY"] = api_key
        if api_secret:
            headers["X-API-SECRET"] = api_secret
        return headers


def mask_secret(raw: str) -> str:
    """Mask secret text for display."""
    if not raw:
        return ""
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}...{raw[-4:]}"

