#!/usr/bin/env python3
"""Stream read-only Upstox five-level NSE equity depth to local JSONL.GZ files."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, time as clock_time
import gzip
import inspect
import json
import os
from pathlib import Path
import sys
import threading
import uuid
from zoneinfo import ZoneInfo

try:
    from _path_setup import BACKEND_ROOT, add_repo_root_to_path
except ModuleNotFoundError:
    from backend.scripts._path_setup import BACKEND_ROOT, add_repo_root_to_path

add_repo_root_to_path()

from backend.src.data.upstox_depth import (
    UPSTOX_FULL_STREAM_LIMIT,
    UpstoxDepthError,
    fetch_nse_equities,
    normalize_v3_stream_message,
    select_daily_equities,
)
from backend.src.utils.config import _reload_environment_values


IST = ZoneInfo("Asia/Kolkata")
DEFAULT_OUTPUT = BACKEND_ROOT / "data" / "liquidity_depth"


class HourlyGzipWriter:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self._hour = ""
        self._file = None
        self._pending = 0
        self._lock = threading.Lock()

    def write(self, records: list[dict]) -> None:
        if not records:
            return
        now = datetime.now(IST)
        hour = now.strftime("%Y-%m-%d/%H")
        with self._lock:
            if hour != self._hour:
                self.close()
                path = self.output_dir / now.strftime("%Y-%m-%d") / f"upstox_full_{now:%H}.jsonl.gz"
                path.parent.mkdir(parents=True, exist_ok=True)
                self._file = gzip.open(
                    path, "at", encoding="utf-8", newline="\n", compresslevel=5
                )
                self._hour = hour
            for record in records:
                self._file.write(json.dumps(record, separators=(",", ":"), allow_nan=False) + "\n")
            self._pending += len(records)
            if self._pending >= 1_000:
                self._file.flush()
                self._pending = 0

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
        self._pending = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stream Upstox V3 full depth for today's maximum rotating NSE equity universe."
    )
    parser.add_argument("--limit", type=int, default=UPSTOX_FULL_STREAM_LIMIT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--market-session",
        action="store_true",
        help="Wait for 09:15 IST and stop at 15:30 IST; used by the scheduled task.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Refresh and report the universe only.")
    return parser.parse_args()


def _session_bounds(now: datetime) -> tuple[datetime, datetime]:
    return (
        datetime.combine(now.date(), clock_time(9, 15), tzinfo=IST),
        datetime.combine(now.date(), clock_time(15, 30), tzinfo=IST),
    )


def _write_manifest(
    output_dir: Path,
    session_date: str,
    available: list[dict],
    selected: list[dict],
) -> Path:
    path = output_dir / session_date / "universe.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "provider": "upstox",
                "feed_mode": "full",
                "session_date": session_date,
                "available_normal_nse_equities": len(available),
                "selected": len(selected),
                "omitted_by_provider_limit": len(available) - len(selected),
                "instruments": selected,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


async def _collect(
    token: str,
    metadata: dict[str, dict],
    writer: HourlyGzipWriter,
    *,
    end_at: datetime | None,
) -> dict[str, int]:
    try:
        import websockets
        from google.protobuf import json_format
        from upstox_client.feeder.proto import MarketDataFeedV3_pb2
    except ImportError as exc:
        raise UpstoxDepthError("Install backend/requirements.txt before recording.") from exc

    request = json.dumps({
        "guid": str(uuid.uuid4()),
        "method": "sub",
        "data": {"mode": "full", "instrumentKeys": list(metadata)},
    }).encode("utf-8")
    counters = {"rows": 0, "skipped": 0}
    reconnect_delay = 5

    while end_at is None or datetime.now(IST) < end_at:
        try:
            header_name = (
                "additional_headers"
                if "additional_headers" in inspect.signature(websockets.connect).parameters
                else "extra_headers"
            )
            async with websockets.connect(
                "wss://api.upstox.com/v3/feed/market-data-feed",
                max_size=None,
                max_queue=1_024,
                ping_interval=20,
                ping_timeout=20,
                **{header_name: {"Authorization": f"Bearer {token}", "Accept": "*/*"}},
            ) as socket:
                await socket.send(request)
                print(f"[connected] Upstox V3 full feed instruments={len(metadata)}")
                while end_at is None or datetime.now(IST) < end_at:
                    timeout = 30.0
                    if end_at is not None:
                        timeout = max(1.0, min(timeout, (end_at - datetime.now(IST)).total_seconds()))
                    try:
                        message = await asyncio.wait_for(socket.recv(), timeout=timeout)
                    except asyncio.TimeoutError:
                        continue
                    decoded = MarketDataFeedV3_pb2.FeedResponse.FromString(message)
                    payload = json_format.MessageToDict(decoded)
                    records, skipped = normalize_v3_stream_message(
                        payload, instrument_metadata=metadata
                    )
                    writer.write(records)
                    counters["rows"] += len(records)
                    counters["skipped"] += len(skipped)
                    if records and counters["rows"] % 10_000 < len(records):
                        print(
                            f"[recording] rows={counters['rows']} "
                            f"skipped={counters['skipped']}"
                        )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            status_code = getattr(exc, "status_code", None) or getattr(
                getattr(exc, "response", None), "status_code", None
            )
            if status_code in {401, 403}:
                raise UpstoxDepthError("Upstox rejected the configured token.") from exc
            if end_at is not None and datetime.now(IST) >= end_at:
                break
            print(f"[feed-error] {exc}; reconnecting in {reconnect_delay}s", file=sys.stderr)
            await asyncio.sleep(reconnect_delay)
    return counters


def main() -> int:
    args = parse_args()
    now = datetime.now(IST)
    if args.market_session and now.weekday() >= 5:
        print("[skip] NSE is closed on weekends.")
        return 0

    session_date = now.date().isoformat()
    available = fetch_nse_equities()
    selected = select_daily_equities(available, session_date, limit=args.limit)
    manifest = _write_manifest(args.output_dir, session_date, available, selected)
    print(
        f"[universe] available={len(available)} selected={len(selected)} "
        f"omitted={len(available) - len(selected)} manifest={manifest}"
    )
    if args.dry_run:
        return 0

    if args.market_session:
        start, end = _session_bounds(now)
        if now >= end:
            print("[skip] Today's NSE session has ended.")
            return 0
        if now < start:
            delay = (start - now).total_seconds()
            print(f"[wait] NSE collection starts at 09:15 IST ({int(delay)} seconds).")
            threading.Event().wait(delay)

    _reload_environment_values(["UPSTOX_ACCESS_TOKEN", "UPSTOX_ANALYTICS_TOKEN"])
    token = os.getenv("UPSTOX_ANALYTICS_TOKEN") or os.getenv("UPSTOX_ACCESS_TOKEN")
    if not token:
        raise UpstoxDepthError(
            "Set UPSTOX_ANALYTICS_TOKEN or UPSTOX_ACCESS_TOKEN in backend/.env."
        )
    metadata = {row["instrument_key"]: row for row in selected}
    writer = HourlyGzipWriter(args.output_dir)
    try:
        print("[info] Read-only collection active; no trading APIs are used.")
        end_at = _session_bounds(datetime.now(IST))[1] if args.market_session else None
        counters = asyncio.run(_collect(token, metadata, writer, end_at=end_at))
    except KeyboardInterrupt:
        print("\n[info] Recording stopped.")
        counters = {"rows": 0, "skipped": 0}
    finally:
        writer.close()
    print(f"[done] rows={counters['rows']} skipped={counters['skipped']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except UpstoxDepthError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(1)
