"""
Qveris historical data service with local cache-first behavior.

Policy:
1) Query local SQLite cache first.
2) Only missing ranges are fetched from Qveris API.
3) Fetched bars are persisted immediately to local cache.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Ensure local source checkout (/workspace) is importable when script is started
# as: python3 examples/crypto_mvp/sync_qveris_history.py
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import BarData

try:
    from examples.crypto_mvp.bar_cache import LocalBarCache
    from examples.crypto_mvp.qveris_client import OhlcvBar, QverisClient
except ModuleNotFoundError:
    from bar_cache import LocalBarCache
    from qveris_client import OhlcvBar, QverisClient


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_vnpy_interval(interval: str) -> Interval | None:
    normalized: str = interval.lower().strip()
    if normalized.endswith("m"):
        return Interval.MINUTE
    if normalized.endswith("h"):
        return Interval.HOUR
    if normalized.endswith("d"):
        return Interval.DAILY
    return None


@dataclass
class FetchStats:
    """Stats for one history request."""

    cache_rows_before: int = 0
    missing_ranges: int = 0
    api_rows_fetched: int = 0
    rows_upserted: int = 0
    final_rows: int = 0


class QverisBacktestDataService:
    """Cache-first history data service."""

    def __init__(self, profile_name: str = "default") -> None:
        self.profile_name = profile_name
        self.provider_name = "QVERIS"
        self.cache = LocalBarCache(profile_name=profile_name)
        self.client = QverisClient(profile_name=profile_name)

    def get_or_fetch_bars(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> tuple[list[OhlcvBar], FetchStats]:
        """Load bars with cache-first + missing-range API backfill."""
        start_utc = _ensure_utc(start)
        end_utc = _ensure_utc(end)

        stats = FetchStats()
        cached_before = self.cache.load_bars(self.provider_name, symbol, interval, start_utc, end_utc)
        stats.cache_rows_before = len(cached_before)

        missing_ranges = self.cache.find_missing_ranges(
            self.provider_name, symbol, interval, start_utc, end_utc
        )
        stats.missing_ranges = len(missing_ranges)

        for gap_start, gap_end in missing_ranges:
            fetched = self.client.fetch_history(symbol, interval, gap_start, gap_end)
            stats.api_rows_fetched += len(fetched)
            stats.rows_upserted += self.cache.upsert_bars(self.provider_name, fetched)

        full_rows = self.cache.load_bars(self.provider_name, symbol, interval, start_utc, end_utc)
        stats.final_rows = len(full_rows)
        return full_rows, stats

    def get_or_fetch_vnpy_bars(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> tuple[list[BarData], FetchStats]:
        """Return cache-first bars in vnpy BarData format."""
        rows, stats = self.get_or_fetch_bars(symbol, interval, start, end)
        vnpy_interval = _to_vnpy_interval(interval)

        bars: list[BarData] = [
            BarData(
                symbol=symbol,
                exchange=Exchange.GLOBAL,
                datetime=row.ts,
                interval=vnpy_interval,
                open_price=row.open_price,
                high_price=row.high_price,
                low_price=row.low_price,
                close_price=row.close_price,
                volume=row.volume,
                turnover=row.turnover,
                open_interest=0,
                gateway_name=self.provider_name,
            )
            for row in rows
        ]
        return bars, stats


def recommended_local_databases() -> list[str]:
    """Recommend open-source local databases for quant workflows."""
    return [
        "SQLite（默认推荐，零部署，适合单机缓存与中小规模回测）",
        "DuckDB（本地分析性能更强，适合因子研究和列式分析）",
        "PostgreSQL + TimescaleDB（多策略并发和时间序列场景）",
    ]

