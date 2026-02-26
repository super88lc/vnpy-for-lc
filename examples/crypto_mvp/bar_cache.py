"""
Local bar cache based on SQLite.

Default database path is managed by LocalProfile settings.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

try:
    from examples.crypto_mvp.local_config import LocalProfile
    from examples.crypto_mvp.qveris_client import OhlcvBar
except ModuleNotFoundError:
    from local_config import LocalProfile
    from qveris_client import OhlcvBar


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _interval_delta(interval: str) -> timedelta:
    normalized: str = interval.strip().lower()
    mapping: dict[str, timedelta] = {
        "1m": timedelta(minutes=1),
        "3m": timedelta(minutes=3),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "30m": timedelta(minutes=30),
        "1h": timedelta(hours=1),
        "2h": timedelta(hours=2),
        "4h": timedelta(hours=4),
        "6h": timedelta(hours=6),
        "12h": timedelta(hours=12),
        "1d": timedelta(days=1),
    }
    if normalized not in mapping:
        raise ValueError(f"不支持的interval: {interval}")
    return mapping[normalized]


def _align_to_step(dt: datetime, step: timedelta) -> datetime:
    epoch: int = int(_ensure_utc(dt).timestamp())
    step_sec: int = int(step.total_seconds())
    aligned: int = epoch - (epoch % step_sec)
    return datetime.fromtimestamp(aligned, tz=timezone.utc)


class LocalBarCache:
    """SQLite-backed bar cache."""

    def __init__(self, profile_name: str = "default") -> None:
        profile = LocalProfile(profile=profile_name)
        settings = profile.load_settings()
        db_path = settings["storage"]["sqlite_path"]
        self.db_path: Path = Path(db_path).expanduser().resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path))
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bars (
                    provider TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    ts INTEGER NOT NULL,
                    open REAL NOT NULL,
                    high REAL NOT NULL,
                    low REAL NOT NULL,
                    close REAL NOT NULL,
                    volume REAL NOT NULL,
                    turnover REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (provider, symbol, interval, ts)
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_bars_lookup
                ON bars (provider, symbol, interval, ts)
                """
            )
            conn.commit()

    def upsert_bars(self, provider: str, bars: list[OhlcvBar]) -> int:
        """Insert or update bars into cache."""
        if not bars:
            return 0

        rows = [
            (
                provider,
                bar.symbol,
                bar.interval,
                int(_ensure_utc(bar.ts).timestamp()),
                bar.open_price,
                bar.high_price,
                bar.low_price,
                bar.close_price,
                bar.volume,
                bar.turnover,
            )
            for bar in bars
        ]
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO bars(
                    provider, symbol, interval, ts, open, high, low, close, volume, turnover
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, symbol, interval, ts) DO UPDATE SET
                    open=excluded.open,
                    high=excluded.high,
                    low=excluded.low,
                    close=excluded.close,
                    volume=excluded.volume,
                    turnover=excluded.turnover
                """,
                rows,
            )
            conn.commit()
        return len(rows)

    def load_bars(
        self,
        provider: str,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[OhlcvBar]:
        """Load bars from cache."""
        start_ts: int = int(_ensure_utc(start).timestamp())
        end_ts: int = int(_ensure_utc(end).timestamp())

        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT ts, open, high, low, close, volume, turnover
                FROM bars
                WHERE provider = ? AND symbol = ? AND interval = ?
                  AND ts >= ? AND ts <= ?
                ORDER BY ts ASC
                """,
                (provider, symbol, interval, start_ts, end_ts),
            )
            rows = cursor.fetchall()

        bars: list[OhlcvBar] = []
        for ts, open_, high, low, close, volume, turnover in rows:
            bars.append(
                OhlcvBar(
                    symbol=symbol,
                    interval=interval,
                    ts=datetime.fromtimestamp(int(ts), tz=timezone.utc),
                    open_price=float(open_),
                    high_price=float(high),
                    low_price=float(low),
                    close_price=float(close),
                    volume=float(volume),
                    turnover=float(turnover),
                )
            )
        return bars

    def find_missing_ranges(
        self,
        provider: str,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[tuple[datetime, datetime]]:
        """Find missing bar ranges in local cache."""
        step: timedelta = _interval_delta(interval)
        aligned_start: datetime = _align_to_step(start, step)
        aligned_end: datetime = _align_to_step(end, step)

        cached = self.load_bars(provider, symbol, interval, aligned_start, aligned_end)
        existing_ts: set[int] = {int(_ensure_utc(bar.ts).timestamp()) for bar in cached}

        missing_ranges: list[tuple[datetime, datetime]] = []
        current: datetime = aligned_start
        gap_start: datetime | None = None
        step_sec: int = int(step.total_seconds())

        while current <= aligned_end:
            current_ts: int = int(_ensure_utc(current).timestamp())
            is_missing: bool = current_ts not in existing_ts

            if is_missing and gap_start is None:
                gap_start = current
            elif (not is_missing) and gap_start is not None:
                gap_end = current - step
                missing_ranges.append((gap_start, gap_end))
                gap_start = None

            current = datetime.fromtimestamp(current_ts + step_sec, tz=timezone.utc)

        if gap_start is not None:
            missing_ranges.append((gap_start, aligned_end))

        return missing_ranges

