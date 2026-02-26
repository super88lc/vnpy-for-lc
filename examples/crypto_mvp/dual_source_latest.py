"""
Dual-source latest market data fetcher (Binance + Qveris).

Example:
    python3 examples/crypto_mvp/dual_source_latest.py \
      --profile default \
      --market spot \
      --symbols BTCUSDT,ETHUSDT \
      --iterations 3
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import sleep
from typing import Any
from urllib.parse import urljoin
import sys

import requests

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from examples.crypto_mvp.local_config import LocalProfile
    from examples.crypto_mvp.qveris_client import QverisClient
except ModuleNotFoundError:
    from local_config import LocalProfile
    from qveris_client import QverisClient


@dataclass
class LatestSnapshot:
    """One-symbol dual-source snapshot."""

    symbol: str
    ts: datetime
    binance_price: float | None
    qveris_price: float | None

    @property
    def delta(self) -> float | None:
        if self.binance_price is None or self.qveris_price is None:
            return None
        return self.binance_price - self.qveris_price

    @property
    def delta_bps(self) -> float | None:
        if self.binance_price is None or self.qveris_price in (None, 0):
            return None
        return (self.binance_price - self.qveris_price) / self.qveris_price * 10000


class BinanceLatestClient:
    """Simple Binance public latest-price client."""

    HOST_MAP: dict[str, str] = {
        "spot": "https://api.binance.com",
        "linear": "https://fapi.binance.com",
        "inverse": "https://dapi.binance.com",
    }

    PATH_MAP: dict[str, str] = {
        "spot": "/api/v3/ticker/price",
        "linear": "/fapi/v1/ticker/price",
        "inverse": "/dapi/v1/ticker/price",
    }

    def __init__(self, market: str, profile_name: str = "default") -> None:
        self.market = market
        self.profile = LocalProfile(profile=profile_name)
        settings = self.profile.load_settings()
        network = settings["network"]
        self.timeout: int = int(network.get("timeout", 15))
        self.proxy_host: str = str(network.get("proxy_host", "")).strip()
        self.proxy_port: int = int(network.get("proxy_port", 0))
        self.session = requests.Session()

    def _proxies(self) -> dict[str, str] | None:
        if not self.proxy_host or self.proxy_port <= 0:
            return None
        proxy = f"http://{self.proxy_host}:{self.proxy_port}"
        return {"http": proxy, "https": proxy}

    def fetch_latest_price(self, symbol: str) -> float:
        host = self.HOST_MAP[self.market]
        path = self.PATH_MAP[self.market]
        url: str = urljoin(host.rstrip("/") + "/", path.lstrip("/"))
        response = self.session.get(
            url,
            params={"symbol": symbol.upper()},
            timeout=self.timeout,
            proxies=self._proxies(),
        )
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        return float(payload["price"])


class DualSourceMarketDataService:
    """Fetch latest prices from Binance and Qveris side-by-side."""

    def __init__(self, profile_name: str = "default", market: str = "spot") -> None:
        self.profile_name = profile_name
        self.market = market
        self.binance = BinanceLatestClient(market=market, profile_name=profile_name)
        self.qveris = QverisClient(profile_name=profile_name)

    def fetch_once(self, symbols: list[str]) -> list[LatestSnapshot]:
        ts = datetime.now(tz=timezone.utc)
        snapshots: list[LatestSnapshot] = []

        for symbol in symbols:
            s = symbol.upper().strip()
            if not s:
                continue

            binance_price: float | None = None
            qveris_price: float | None = None

            try:
                binance_price = self.binance.fetch_latest_price(s)
            except Exception as exc:
                print(f"[WARN] Binance 拉取失败 {s}: {exc}")

            try:
                qveris_price = self.qveris.fetch_latest_price(s)
            except Exception as exc:
                print(f"[WARN] Qveris 拉取失败 {s}: {exc}")

            snapshots.append(
                LatestSnapshot(
                    symbol=s,
                    ts=ts,
                    binance_price=binance_price,
                    qveris_price=qveris_price,
                )
            )

        return snapshots


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dual-source latest market data (Binance + Qveris)")
    parser.add_argument("--profile", default="default", help="Local profile name")
    parser.add_argument("--market", choices=["spot", "linear", "inverse"], default="spot")
    parser.add_argument(
        "--symbols",
        required=True,
        help="Comma-separated symbols, e.g. BTCUSDT,ETHUSDT",
    )
    parser.add_argument("--poll-seconds", type=float, default=2.0, help="Polling interval seconds")
    parser.add_argument("--iterations", type=int, default=1, help="How many polling loops to run")
    return parser


def print_snapshot(snapshot: LatestSnapshot) -> None:
    delta = snapshot.delta
    delta_bps = snapshot.delta_bps

    delta_str: str = f"{delta:.8f}" if delta is not None else "N/A"
    delta_bps_str: str = f"{delta_bps:.3f}" if delta_bps is not None else "N/A"
    binance_str: str = f"{snapshot.binance_price:.8f}" if snapshot.binance_price is not None else "N/A"
    qveris_str: str = f"{snapshot.qveris_price:.8f}" if snapshot.qveris_price is not None else "N/A"

    print(
        f"[{snapshot.ts.strftime('%H:%M:%S')}] {snapshot.symbol} "
        f"Binance={binance_str} Qveris={qveris_str} "
        f"Delta={delta_str} Delta(bps)={delta_bps_str}"
    )


def main() -> int:
    args = build_parser().parse_args()
    symbols: list[str] = [item.strip().upper() for item in args.symbols.split(",") if item.strip()]
    service = DualSourceMarketDataService(profile_name=args.profile, market=args.market)

    for i in range(args.iterations):
        snapshots = service.fetch_once(symbols)
        for snapshot in snapshots:
            print_snapshot(snapshot)

        if i < args.iterations - 1:
            sleep(args.poll_seconds)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
