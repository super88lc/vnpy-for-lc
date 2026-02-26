"""
Qveris data source client for crypto MVP.

Notes:
- Qveris API schema may differ by deployment. This client supports configurable
  endpoint and response field mapping through local profile settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin

import requests

from local_config import LocalProfile


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_iso_z(dt: datetime) -> str:
    return _ensure_utc(dt).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: Any) -> datetime:
    """Parse timestamp from int/float/ISO text."""
    if isinstance(value, datetime):
        return _ensure_utc(value)

    if isinstance(value, (int, float)):
        # Heuristic: value > 1e12 usually means milliseconds.
        if value > 1_000_000_000_000:
            value = value / 1000
        return datetime.fromtimestamp(float(value), tz=timezone.utc)

    if isinstance(value, str):
        raw: str = value.strip()
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        # Try ISO parse first.
        try:
            return _ensure_utc(datetime.fromisoformat(raw))
        except ValueError:
            pass
        # Numeric string fallback.
        try:
            num = float(raw)
            if num > 1_000_000_000_000:
                num = num / 1000
            return datetime.fromtimestamp(num, tz=timezone.utc)
        except ValueError as exc:
            raise ValueError(f"无法解析时间戳: {value}") from exc

    raise ValueError(f"不支持的时间戳类型: {type(value)}")


def _extract_items(payload: Any, data_field: str) -> list[dict[str, Any]]:
    """Extract row list from multiple response shapes."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]

    if isinstance(payload, dict):
        if data_field and data_field in payload:
            data_obj = payload[data_field]
            if isinstance(data_obj, list):
                return [row for row in data_obj if isinstance(row, dict)]
            if isinstance(data_obj, dict):
                for key in ("items", "rows", "result", "records"):
                    obj = data_obj.get(key)
                    if isinstance(obj, list):
                        return [row for row in obj if isinstance(row, dict)]

        for key in ("data", "items", "rows", "result", "records"):
            obj = payload.get(key)
            if isinstance(obj, list):
                return [row for row in obj if isinstance(row, dict)]
            if isinstance(obj, dict):
                nested = obj.get("items") or obj.get("rows") or obj.get("records")
                if isinstance(nested, list):
                    return [row for row in nested if isinstance(row, dict)]

    return []


@dataclass
class OhlcvBar:
    """Standardized OHLCV row."""

    symbol: str
    interval: str
    ts: datetime
    open_price: float
    high_price: float
    low_price: float
    close_price: float
    volume: float
    turnover: float = 0.0


class QverisClient:
    """Qveris HTTP client with configurable schema."""

    def __init__(self, profile_name: str = "default", timeout: int | None = None) -> None:
        self.profile = LocalProfile(profile=profile_name)
        settings: dict[str, Any] = self.profile.load_settings()
        network: dict[str, Any] = settings["network"]
        qveris: dict[str, Any] = settings["qveris"]

        self.base_url: str = str(qveris.get("base_url", "")).strip()
        self.history_endpoint: str = str(qveris.get("history_endpoint", "/v1/crypto/history"))
        self.latest_endpoint: str = str(qveris.get("latest_endpoint", "/v1/crypto/latest"))
        self.symbol_param: str = str(qveris.get("symbol_param", "symbol"))
        self.interval_param: str = str(qveris.get("interval_param", "interval"))
        self.start_param: str = str(qveris.get("start_param", "start"))
        self.end_param: str = str(qveris.get("end_param", "end"))
        self.response_data_field: str = str(qveris.get("response_data_field", "data"))
        self.field_map: dict[str, str] = dict(qveris.get("field_map", {}))

        self.timeout: int = int(timeout if timeout is not None else network.get("timeout", 15))
        self.proxy_host: str = str(network.get("proxy_host", "")).strip()
        self.proxy_port: int = int(network.get("proxy_port", 0))
        self.session: requests.Session = requests.Session()

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        headers.update(self.profile.build_qveris_auth_headers())
        return headers

    def _build_proxies(self) -> dict[str, str] | None:
        if not self.proxy_host or self.proxy_port <= 0:
            return None
        proxy = f"http://{self.proxy_host}:{self.proxy_port}"
        return {"http": proxy, "https": proxy}

    def _history_url(self) -> str:
        if not self.base_url:
            raise RuntimeError("Qveris base_url 未配置，请先执行 config_cli.py set-qveris")
        return urljoin(self.base_url.rstrip("/") + "/", self.history_endpoint.lstrip("/"))

    def _latest_url(self) -> str:
        if not self.base_url:
            raise RuntimeError("Qveris base_url 未配置，请先执行 config_cli.py set-qveris")
        return urljoin(self.base_url.rstrip("/") + "/", self.latest_endpoint.lstrip("/"))

    def _field(self, mapping_key: str, default_keys: tuple[str, ...], row: dict[str, Any]) -> Any:
        mapped_name: str = str(self.field_map.get(mapping_key, "")).strip()
        if mapped_name and mapped_name in row:
            return row[mapped_name]

        for key in default_keys:
            if key in row:
                return row[key]
        return None

    def fetch_history(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> list[OhlcvBar]:
        """Fetch historical bars from Qveris API."""
        params: dict[str, str] = {
            self.symbol_param: symbol,
            self.interval_param: interval,
            self.start_param: _to_iso_z(start),
            self.end_param: _to_iso_z(end),
        }
        response = self.session.get(
            self._history_url(),
            params=params,
            headers=self._build_headers(),
            timeout=self.timeout,
            proxies=self._build_proxies(),
        )
        response.raise_for_status()

        payload: Any = response.json()
        rows: list[dict[str, Any]] = _extract_items(payload, self.response_data_field)

        bars: list[OhlcvBar] = []
        for row in rows:
            ts_raw = self._field("timestamp", ("timestamp", "ts", "time", "datetime", "open_time"), row)
            open_raw = self._field("open", ("open", "o"), row)
            high_raw = self._field("high", ("high", "h"), row)
            low_raw = self._field("low", ("low", "l"), row)
            close_raw = self._field("close", ("close", "c"), row)
            volume_raw = self._field("volume", ("volume", "v"), row)
            turnover_raw = self._field("turnover", ("turnover", "quote_volume"), row)

            if ts_raw is None or open_raw is None or high_raw is None or low_raw is None or close_raw is None:
                continue

            bars.append(
                OhlcvBar(
                    symbol=symbol,
                    interval=interval,
                    ts=_parse_timestamp(ts_raw),
                    open_price=float(open_raw),
                    high_price=float(high_raw),
                    low_price=float(low_raw),
                    close_price=float(close_raw),
                    volume=float(volume_raw or 0.0),
                    turnover=float(turnover_raw or 0.0),
                )
            )

        bars.sort(key=lambda b: b.ts)
        return bars

    def fetch_latest_price(self, symbol: str) -> float:
        """Fetch latest price for one symbol."""
        params: dict[str, str] = {self.symbol_param: symbol}
        response = self.session.get(
            self._latest_url(),
            params=params,
            headers=self._build_headers(),
            timeout=self.timeout,
            proxies=self._build_proxies(),
        )
        response.raise_for_status()
        payload: Any = response.json()
        rows: list[dict[str, Any]] = _extract_items(payload, self.response_data_field)

        if rows:
            row = rows[0]
            price = row.get("price", row.get("last", row.get("close")))
            if price is None:
                raise RuntimeError(f"Qveris latest payload缺少价格字段: {row}")
            return float(price)

        if isinstance(payload, dict):
            # fallback for flat payload
            price = payload.get("price", payload.get("last", payload.get("close")))
            if price is not None:
                return float(price)

        raise RuntimeError(f"Qveris latest payload无法解析价格: {payload}")

