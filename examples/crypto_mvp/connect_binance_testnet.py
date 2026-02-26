"""
Binance testnet connectivity probe for VeighNa Crypto MVP.

Usage:
    python3 examples/crypto_mvp/connect_binance_testnet.py --market spot
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic, sleep

# Ensure local source checkout (/workspace) is importable when script is started
# as: python3 examples/crypto_mvp/connect_binance_testnet.py
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from vnpy.event import Event, EventEngine
from vnpy.trader.constant import Exchange
from vnpy.trader.engine import MainEngine
from vnpy.trader.event import EVENT_ACCOUNT, EVENT_CONTRACT, EVENT_LOG, EVENT_TICK
from vnpy.trader.object import AccountData, ContractData, LogData, SubscribeRequest, TickData

try:
    from vnpy_binance import BinanceInverseGateway, BinanceLinearGateway, BinanceSpotGateway
except ModuleNotFoundError as exc:
    raise RuntimeError(
        "缺少 vnpy_binance，请先执行: python3 -m pip install --upgrade vnpy_binance"
    ) from exc


ERROR_KEYWORDS: tuple[str, ...] = (
    "failed",
    "error",
    "exception",
    "invalid",
    "forbidden",
    "denied",
    "timeout",
    "signature",
    "timestamp",
    "-20",         # Binance 常见错误码前缀，如 -2015
)


@dataclass
class ProbeState:
    """In-memory probe state."""

    accounts: set[str] = field(default_factory=set)
    contracts: set[str] = field(default_factory=set)
    ticks: int = 0
    log_count: int = 0
    error_logs: list[str] = field(default_factory=list)
    subscribed: bool = False


def parse_bool(value: str) -> bool:
    """Parse bool from string."""
    lowered: str = value.strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise argparse.ArgumentTypeError(f"无法解析布尔值: {value}")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Binance testnet connectivity probe")
    parser.add_argument(
        "--market",
        choices=["spot", "linear", "inverse"],
        default="spot",
        help="Binance market type.",
    )
    parser.add_argument(
        "--server",
        choices=["TESTNET", "REAL"],
        default="TESTNET",
        help="Server target. For key verification, TESTNET is recommended.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=25,
        help="Probe timeout in seconds.",
    )
    parser.add_argument(
        "--symbol",
        default="",
        help="Optional symbol for tick subscription test, e.g. BTCUSDT.",
    )
    parser.add_argument(
        "--kline-stream",
        type=parse_bool,
        default=True,
        help="Whether to enable kline stream subscription (true/false).",
    )
    parser.add_argument("--proxy-host", default="", help="Proxy host.")
    parser.add_argument("--proxy-port", type=int, default=0, help="Proxy port.")
    parser.add_argument("--api-key", default="", help="Binance API key.")
    parser.add_argument("--api-secret", default="", help="Binance API secret.")
    parser.add_argument(
        "--stop-on-success",
        type=parse_bool,
        default=True,
        help="Stop early once probe criteria are met (true/false).",
    )
    return parser.parse_args()


def getenv_first(names: list[str]) -> str:
    """Return first non-empty environment variable."""
    for name in names:
        value: str = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def resolve_credentials(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve API key/secret from args or environment variables."""
    prefix_map: dict[str, str] = {
        "spot": "BINANCE_SPOT",
        "linear": "BINANCE_LINEAR",
        "inverse": "BINANCE_INVERSE",
    }
    prefix: str = prefix_map[args.market]

    api_key: str = args.api_key.strip() or getenv_first(
        [f"{prefix}_API_KEY", "BINANCE_API_KEY"]
    )
    api_secret: str = args.api_secret.strip() or getenv_first(
        [f"{prefix}_API_SECRET", "BINANCE_API_SECRET"]
    )
    return api_key, api_secret


def choose_gateway(market: str) -> type:
    """Choose gateway class by market."""
    gateway_map: dict[str, type] = {
        "spot": BinanceSpotGateway,
        "linear": BinanceLinearGateway,
        "inverse": BinanceInverseGateway,
    }
    return gateway_map[market]


def mask_key(value: str) -> str:
    """Mask sensitive key for logging."""
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def main() -> int:
    """Program entry."""
    args = parse_args()
    api_key, api_secret = resolve_credentials(args)

    if not api_key or not api_secret:
        print("[ERROR] 未检测到 Binance API Key/Secret。")
        print("[HINT] 可通过参数或环境变量传入：")
        print("       --api-key / --api-secret")
        print("       BINANCE_<MARKET>_API_KEY / BINANCE_<MARKET>_API_SECRET")
        print("       BINANCE_API_KEY / BINANCE_API_SECRET")
        return 2

    gateway_class = choose_gateway(args.market)
    gateway_name: str = gateway_class.default_name
    state = ProbeState()

    print("[INFO] ===== Binance 连接探测开始 =====")
    print(f"[INFO] market={args.market}, server={args.server}, gateway={gateway_name}")
    print(f"[INFO] api_key={mask_key(api_key)}")

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)

    def on_log(event: Event) -> None:
        log: LogData = event.data
        state.log_count += 1
        msg: str = log.msg.strip()
        print(f"[LOG] {log.time.strftime('%H:%M:%S')} {msg}")

        lowered = msg.lower()
        if any(keyword in lowered for keyword in ERROR_KEYWORDS):
            if msg not in state.error_logs:
                state.error_logs.append(msg)

    def on_account(event: Event) -> None:
        account: AccountData = event.data
        if account.vt_accountid not in state.accounts:
            state.accounts.add(account.vt_accountid)
            print(
                "[ACCOUNT] "
                f"id={account.vt_accountid}, balance={account.balance:.6f}, available={account.available:.6f}"
            )

    def on_contract(event: Event) -> None:
        contract: ContractData = event.data
        if contract.vt_symbol in state.contracts:
            return

        state.contracts.add(contract.vt_symbol)
        if len(state.contracts) <= 5:
            print(f"[CONTRACT] {contract.vt_symbol}, pricetick={contract.pricetick}, size={contract.size}")
        elif len(state.contracts) == 6:
            print("[CONTRACT] 合约事件较多，后续省略展示...")

    def on_tick(event: Event) -> None:
        tick: TickData = event.data
        state.ticks += 1
        if state.ticks <= 3:
            print(f"[TICK] {tick.vt_symbol} last={tick.last_price}")

    event_engine.register(EVENT_LOG, on_log)
    event_engine.register(EVENT_ACCOUNT, on_account)
    event_engine.register(EVENT_CONTRACT, on_contract)
    event_engine.register(EVENT_TICK, on_tick)

    main_engine.add_gateway(gateway_class)

    setting: dict[str, str | int] = {
        "API Key": api_key,
        "API Secret": api_secret,
        "Server": args.server,
        "Kline Stream": "True" if args.kline_stream else "False",
        "Proxy Host": args.proxy_host or os.getenv("BINANCE_PROXY_HOST", "").strip(),
        "Proxy Port": args.proxy_port or int(os.getenv("BINANCE_PROXY_PORT", "0") or "0"),
    }

    target_symbol: str = args.symbol.strip().upper()
    subscribed_symbol: str = ""
    deadline: float = monotonic() + args.timeout

    try:
        main_engine.connect(setting, gateway_name)

        while monotonic() < deadline:
            # Subscribe after contract info is available to reduce symbol typo noise.
            if target_symbol and not state.subscribed and state.contracts:
                req = SubscribeRequest(symbol=target_symbol, exchange=Exchange.GLOBAL)
                main_engine.subscribe(req, gateway_name)
                state.subscribed = True
                subscribed_symbol = target_symbol
                print(f"[INFO] 已发起行情订阅: {target_symbol}.GLOBAL")

            base_success: bool = bool(state.accounts) and bool(state.contracts)
            tick_success: bool = (not target_symbol) or state.ticks > 0

            if args.stop_on_success and base_success and tick_success:
                print("[INFO] 已满足成功条件，提前结束探测。")
                break

            sleep(1)
    finally:
        main_engine.close()

    base_success = bool(state.accounts) and bool(state.contracts)
    tick_success = (not target_symbol) or state.ticks > 0
    success: bool = base_success and tick_success

    print("[INFO] ===== Binance 连接探测总结 =====")
    print(f"[SUMMARY] accounts={len(state.accounts)}, contracts={len(state.contracts)}, ticks={state.ticks}")
    if subscribed_symbol:
        print(f"[SUMMARY] subscribed_symbol={subscribed_symbol}")
    if state.error_logs:
        print("[SUMMARY] 关键错误日志：")
        for msg in state.error_logs[:5]:
            print(f"  - {msg}")

    if success:
        print("[PASS] 测试通过：API Key可用，网关连接链路已打通。")
        return 0

    joined_errors: str = " | ".join(state.error_logs).lower()

    print("[FAIL] 测试未通过：未在超时时间内拿到账户/合约/行情关键事件。")
    print("[HINT] 常见排查方向：")
    print("  1) API Key/Secret 是否来自正确测试网（spot 与 futures 不通用）")
    print("  2) 是否启用了IP白名单且当前出口IP不在列表中")
    print("  3) 云主机时间是否漂移（timestamp/signature相关错误）")
    print("  4) 代理配置是否正确（Proxy Host/Port）")
    if "restricted location" in joined_errors or " 451" in joined_errors:
        print("  5) 当前出口IP可能触发Binance地区限制（451），请更换网络出口或代理")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
