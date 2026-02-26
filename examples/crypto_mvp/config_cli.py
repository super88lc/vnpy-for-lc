"""
Interactive CLI for local-only crypto MVP configuration.

All profile files are written to:
    ~/.vntrader/crypto_mvp/profiles/
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from getpass import getpass
from pathlib import Path
from typing import Any

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from examples.crypto_mvp.local_config import (
        PROFILES_DIR,
        LocalProfile,
        ROOT_DIR,
        ensure_dirs,
        mask_secret,
    )
except ModuleNotFoundError:
    from local_config import (
        PROFILES_DIR,
        LocalProfile,
        ROOT_DIR,
        ensure_dirs,
        mask_secret,
    )


def parse_bool(value: str) -> bool:
    """Parse bool from command line string."""
    lowered: str = value.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"无法解析布尔值: {value}")


def input_with_default(prompt: str, default: str) -> str:
    """Read input with default fallback."""
    value: str = input(f"{prompt} [{default}]: ").strip()
    return value or default


def print_json_like(data: dict[str, Any], indent: int = 0) -> None:
    """Simple dict printer without importing json for formatting logic."""
    pad: str = " " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            print(f"{pad}{key}:")
            print_json_like(value, indent + 2)
        else:
            print(f"{pad}{key}: {value}")


def cmd_wizard(profile: LocalProfile) -> int:
    """Interactive one-stop setup wizard."""
    settings = profile.load_settings()
    secrets = profile.load_secrets()

    print("=== Crypto MVP 本地配置向导 ===")
    print(f"Profile: {profile.profile}")
    print(f"配置目录: {ROOT_DIR}")

    proxy_host: str = input_with_default("Proxy Host", str(settings["network"]["proxy_host"]))
    proxy_port: int = int(input_with_default("Proxy Port", str(settings["network"]["proxy_port"])))
    timeout: int = int(input_with_default("Network Timeout(sec)", str(settings["network"]["timeout"])))

    market: str = input_with_default("Binance market (spot/linear/inverse)", settings["binance"]["market"])
    server: str = input_with_default("Binance server (TESTNET/REAL)", settings["binance"]["server"])
    kline_stream: bool = parse_bool(
        input_with_default("Binance Kline Stream (true/false)", str(settings["binance"]["kline_stream"]))
    )

    api_key: str = getpass("Binance API Key (输入留空则保持不变): ").strip()
    api_secret: str = getpass("Binance API Secret (输入留空则保持不变): ").strip()

    qveris_base_url: str = input_with_default("Qveris Base URL", settings["qveris"]["base_url"])
    qveris_history_endpoint: str = input_with_default(
        "Qveris History Endpoint", settings["qveris"]["history_endpoint"]
    )
    qveris_latest_endpoint: str = input_with_default(
        "Qveris Latest Endpoint", settings["qveris"]["latest_endpoint"]
    )
    qveris_api_key: str = getpass("Qveris API Key (输入留空则保持不变): ").strip()
    qveris_api_secret: str = getpass("Qveris API Secret (输入留空则保持不变): ").strip()

    profile.update_settings(
        {
            "network": {
                "proxy_host": proxy_host,
                "proxy_port": proxy_port,
                "timeout": timeout,
            },
            "binance": {
                "market": market,
                "server": server,
                "kline_stream": kline_stream,
            },
            "qveris": {
                "base_url": qveris_base_url,
                "history_endpoint": qveris_history_endpoint,
                "latest_endpoint": qveris_latest_endpoint,
            },
        }
    )

    secret_patch: dict[str, Any] = {}
    if api_key or api_secret:
        secret_patch["binance"] = {
            market: {
                "api_key": api_key or secrets["binance"][market]["api_key"],
                "api_secret": api_secret or secrets["binance"][market]["api_secret"],
            }
        }
    if qveris_api_key or qveris_api_secret:
        secret_patch["qveris"] = {
            "api_key": qveris_api_key or secrets["qveris"]["api_key"],
            "api_secret": qveris_api_secret or secrets["qveris"]["api_secret"],
        }
    if secret_patch:
        profile.update_secrets(secret_patch)

    print("[OK] 配置完成并写入本地目录（不在git仓库中）。")
    return 0


def cmd_set_proxy(profile: LocalProfile, args: argparse.Namespace) -> int:
    """Update proxy settings."""
    proxy_host: str = args.host
    proxy_port: int = args.port
    timeout: int = args.timeout

    if args.interactive:
        current = profile.load_settings()["network"]
        proxy_host = input_with_default("Proxy Host", str(current["proxy_host"]))
        proxy_port = int(input_with_default("Proxy Port", str(current["proxy_port"])))
        timeout = int(input_with_default("Network Timeout(sec)", str(current["timeout"])))

    profile.update_settings(
        {
            "network": {
                "proxy_host": proxy_host,
                "proxy_port": proxy_port,
                "timeout": timeout,
            }
        }
    )
    print("[OK] 已更新代理配置。")
    return 0


def cmd_set_binance(profile: LocalProfile, args: argparse.Namespace) -> int:
    """Update binance settings and optional secrets."""
    profile.update_settings(
        {
            "binance": {
                "market": args.market,
                "server": args.server,
                "kline_stream": args.kline_stream,
            }
        }
    )

    api_key: str = args.api_key.strip()
    api_secret: str = args.api_secret.strip()
    if args.interactive:
        api_key = getpass("Binance API Key (输入留空则不更新): ").strip()
        api_secret = getpass("Binance API Secret (输入留空则不更新): ").strip()

    if api_key or api_secret:
        existing = profile.load_secrets()["binance"][args.market]
        profile.update_secrets(
            {
                "binance": {
                    args.market: {
                        "api_key": api_key or existing["api_key"],
                        "api_secret": api_secret or existing["api_secret"],
                    }
                }
            }
        )

    print(f"[OK] 已更新 Binance({args.market}) 配置。")
    return 0


def cmd_set_qveris(profile: LocalProfile, args: argparse.Namespace) -> int:
    """Update qveris settings and optional secrets."""
    profile.update_settings(
        {
            "qveris": {
                "base_url": args.base_url,
                "history_endpoint": args.history_endpoint,
                "latest_endpoint": args.latest_endpoint,
            }
        }
    )

    api_key: str = args.api_key.strip()
    api_secret: str = args.api_secret.strip()
    if args.interactive:
        api_key = getpass("Qveris API Key (输入留空则不更新): ").strip()
        api_secret = getpass("Qveris API Secret (输入留空则不更新): ").strip()

    if api_key or api_secret:
        existing = profile.load_secrets()["qveris"]
        profile.update_secrets(
            {
                "qveris": {
                    "api_key": api_key or existing["api_key"],
                    "api_secret": api_secret or existing["api_secret"],
                }
            }
        )

    print("[OK] 已更新 Qveris 配置。")
    return 0


def cmd_show(profile: LocalProfile, show_secrets: bool) -> int:
    """Print current profile settings."""
    settings = profile.load_settings()
    secrets = profile.load_secrets()

    print(f"Profile: {profile.profile}")
    print(f"Settings path: {PROFILES_DIR / (profile.profile + '.settings.json')}")
    print(f"Secrets path: {PROFILES_DIR / (profile.profile + '.secrets.json')}")
    print("\n[settings]")
    print_json_like(settings, 2)

    print("\n[secrets]")
    display_secrets: dict[str, Any] = {
        "binance": {},
        "qveris": {},
    }
    for market in ("spot", "linear", "inverse"):
        info = secrets["binance"][market]
        display_secrets["binance"][market] = {
            "api_key": info["api_key"] if show_secrets else mask_secret(info["api_key"]),
            "api_secret": info["api_secret"] if show_secrets else mask_secret(info["api_secret"]),
        }
    display_secrets["qveris"] = {
        "api_key": secrets["qveris"]["api_key"] if show_secrets else mask_secret(secrets["qveris"]["api_key"]),
        "api_secret": secrets["qveris"]["api_secret"] if show_secrets else mask_secret(secrets["qveris"]["api_secret"]),
    }
    print_json_like(display_secrets, 2)
    return 0


def cmd_security_check() -> int:
    """Check common secret-leak risks in git tracked files."""
    suspicious_patterns: tuple[str, ...] = (
        ".env",
        ".secrets",
        "api_key",
        "api-secret",
        "private_key",
    )

    try:
        completed = subprocess.run(
            ["git", "ls-files"],
            cwd=str(PROJECT_ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        print(f"[WARN] 无法执行 git ls-files: {exc}")
        return 1

    tracked_files: list[str] = [line.strip() for line in completed.stdout.splitlines() if line.strip()]

    matched: list[str] = []
    for path in tracked_files:
        lowered = path.lower()
        if lowered.endswith(".env.example") or lowered.endswith("env.example"):
            continue
        if any(token in lowered for token in suspicious_patterns):
            matched.append(path)

    print("=== Security Check ===")
    print(f"本地配置目录: {ROOT_DIR}")
    print("建议：所有真实Key只放在该目录，不放仓库。")

    if matched:
        print("[WARN] 检测到可能含敏感信息的已跟踪文件名：")
        for item in matched:
            print(f"  - {item}")
        return 2

    print("[OK] 未发现明显敏感命名的已跟踪文件。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build top-level parser."""
    parser = argparse.ArgumentParser(description="Crypto MVP local config CLI")
    parser.add_argument("--profile", default="default", help="Local profile name.")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("wizard", help="Interactive setup wizard.")

    set_proxy = subparsers.add_parser("set-proxy", help="Set proxy/network settings.")
    set_proxy.add_argument("--host", default="", help="Proxy host.")
    set_proxy.add_argument("--port", type=int, default=0, help="Proxy port.")
    set_proxy.add_argument("--timeout", type=int, default=15, help="Network timeout in seconds.")
    set_proxy.add_argument("--interactive", action="store_true", help="Use interactive prompts.")

    set_binance = subparsers.add_parser("set-binance", help="Set binance gateway settings.")
    set_binance.add_argument("--market", choices=["spot", "linear", "inverse"], default="spot")
    set_binance.add_argument("--server", choices=["TESTNET", "REAL"], default="TESTNET")
    set_binance.add_argument("--kline-stream", type=parse_bool, default=True)
    set_binance.add_argument("--api-key", default="", help="Binance API key.")
    set_binance.add_argument("--api-secret", default="", help="Binance API secret.")
    set_binance.add_argument("--interactive", action="store_true", help="Prompt key/secret securely.")

    set_qveris = subparsers.add_parser("set-qveris", help="Set qveris data source settings.")
    set_qveris.add_argument("--base-url", default="")
    set_qveris.add_argument("--history-endpoint", default="/v1/crypto/history")
    set_qveris.add_argument("--latest-endpoint", default="/v1/crypto/latest")
    set_qveris.add_argument("--api-key", default="")
    set_qveris.add_argument("--api-secret", default="")
    set_qveris.add_argument("--interactive", action="store_true", help="Prompt key/secret securely.")

    show = subparsers.add_parser("show", help="Show current profile values.")
    show.add_argument("--show-secrets", action="store_true", help="Print secrets in plain text.")

    subparsers.add_parser("security-check", help="Check git tracked file names for leak risks.")
    return parser


def main() -> int:
    """Program entry."""
    ensure_dirs()
    parser = build_parser()
    args = parser.parse_args()
    profile = LocalProfile(profile=args.profile)

    if args.command == "wizard":
        return cmd_wizard(profile)
    if args.command == "set-proxy":
        return cmd_set_proxy(profile, args)
    if args.command == "set-binance":
        return cmd_set_binance(profile, args)
    if args.command == "set-qveris":
        return cmd_set_qveris(profile, args)
    if args.command == "show":
        return cmd_show(profile, args.show_secrets)
    if args.command == "security-check":
        return cmd_security_check()

    parser.error(f"未知命令: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
