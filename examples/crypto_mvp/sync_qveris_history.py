"""
Sync Qveris history into local cache (cache-first).

Example:
    python3 examples/crypto_mvp/sync_qveris_history.py \
      --profile default \
      --symbol BTCUSDT \
      --interval 1m \
      --start 2026-01-01T00:00:00Z \
      --end 2026-01-02T00:00:00Z
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from examples.crypto_mvp.qveris_backtest_data import (
        QverisBacktestDataService,
        recommended_local_databases,
    )
except ModuleNotFoundError:
    from qveris_backtest_data import QverisBacktestDataService, recommended_local_databases


def parse_datetime(value: str) -> datetime:
    """Parse datetime from ISO text."""
    raw = value.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Qveris history sync with local cache")
    parser.add_argument("--profile", default="default", help="Local profile name")
    parser.add_argument("--symbol", required=True, help="Trading symbol, e.g. BTCUSDT")
    parser.add_argument("--interval", default="1m", help="Bar interval, e.g. 1m/5m/1h/1d")
    parser.add_argument("--start", required=True, help="Start time in ISO format")
    parser.add_argument("--end", required=True, help="End time in ISO format")
    parser.add_argument(
        "--print-db-recommendation",
        action="store_true",
        help="Print recommended local open-source databases.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    start = parse_datetime(args.start)
    end = parse_datetime(args.end)

    try:
        service = QverisBacktestDataService(profile_name=args.profile)
        rows, stats = service.get_or_fetch_bars(args.symbol.upper(), args.interval, start, end)
    except Exception as exc:
        print(f"[FAIL] 历史数据同步失败: {exc}")
        print("[HINT] 请先执行：")
        print(
            "  python3 examples/crypto_mvp/config_cli.py "
            f"--profile {args.profile} set-qveris --base-url \"https://your-qveris-endpoint\""
        )
        return 2

    print("[INFO] ===== Qveris历史数据同步完成 =====")
    print(f"[SUMMARY] symbol={args.symbol.upper()} interval={args.interval}")
    print(f"[SUMMARY] cache_rows_before={stats.cache_rows_before}")
    print(f"[SUMMARY] missing_ranges={stats.missing_ranges}")
    print(f"[SUMMARY] api_rows_fetched={stats.api_rows_fetched}")
    print(f"[SUMMARY] rows_upserted={stats.rows_upserted}")
    print(f"[SUMMARY] final_rows={stats.final_rows}")
    print(f"[SUMMARY] cache_db={service.cache.db_path}")

    if rows:
        print(f"[SAMPLE] first={rows[0].ts.isoformat()} close={rows[0].close_price}")
        print(f"[SAMPLE] last={rows[-1].ts.isoformat()} close={rows[-1].close_price}")

    if args.print_db_recommendation:
        print("[INFO] 推荐本地开源数据库：")
        for item in recommended_local_databases():
            print(f"  - {item}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
