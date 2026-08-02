#!/usr/bin/env python3
"""Record read-only Upstox five-level depth snapshots as JSONL."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys
import time

try:
    from _path_setup import BACKEND_ROOT, add_repo_root_to_path
except ModuleNotFoundError:
    from backend.scripts._path_setup import BACKEND_ROOT, add_repo_root_to_path

add_repo_root_to_path()

from backend.src.data.upstox_depth import (
    UpstoxDepthError,
    UpstoxDepthRecorder,
    load_instrument_universe,
)


DEFAULT_UNIVERSE = BACKEND_ROOT / "config" / "liquidity_universe.v1.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Append read-only Upstox market-depth snapshots to a local JSONL file."
    )
    parser.add_argument(
        "--instrument-key",
        action="append",
        dest="instrument_keys",
        help="Upstox instrument key; repeat for multiple instruments.",
    )
    parser.add_argument(
        "--universe",
        type=Path,
        default=DEFAULT_UNIVERSE,
        help="Versioned instrument-universe JSON used when no manual keys are supplied.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=1.0,
        help="Delay between snapshots (default: 1.0).",
    )
    parser.add_argument(
        "--samples",
        type=int,
        help="Stop after this many polling rounds; otherwise run until Ctrl+C.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="JSONL output path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.interval_seconds <= 0:
        raise SystemExit("--interval-seconds must be positive.")
    if args.samples is not None and args.samples <= 0:
        raise SystemExit("--samples must be positive.")

    output = args.output or (
        BACKEND_ROOT
        / "data"
        / "liquidity_depth"
        / f"upstox_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
    )
    universe = None if args.instrument_keys else load_instrument_universe(args.universe)
    instruments = universe["instruments"] if universe else []
    instrument_keys = args.instrument_keys or [row["instrument_key"] for row in instruments]
    metadata = {row["instrument_key"]: row for row in instruments}
    recorder = UpstoxDepthRecorder(
        instrument_keys=instrument_keys,
        output_path=output,
        universe_version=universe["version"] if universe else None,
        instrument_metadata=metadata,
    )

    rounds = 0
    rows = 0
    if universe:
        print(f"[info] Universe {universe['version']} instruments={len(instrument_keys)}")
    print(f"[info] Recording read-only depth to {output}")
    try:
        while args.samples is None or rounds < args.samples:
            started = time.monotonic()
            records = recorder.capture_once()
            rounds += 1
            rows += len(records)
            print(f"[ok] round={rounds} rows={rows} skipped={len(recorder.last_skipped)}")
            for instrument_key, reason in recorder.last_skipped.items():
                print(f"[warning] {instrument_key}: {reason}", file=sys.stderr)
            delay = args.interval_seconds - (time.monotonic() - started)
            if delay > 0 and (args.samples is None or rounds < args.samples):
                time.sleep(delay)
    except KeyboardInterrupt:
        print("\n[info] Recording stopped.")
    except UpstoxDepthError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1

    print(f"[done] rounds={rounds} rows={rows} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
