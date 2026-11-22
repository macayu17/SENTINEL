"""Import and normalization for NSE chart and quote-history CSV exports."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class HistoricalPoint:
    timestamp: str
    price: float


@dataclass(frozen=True)
class HistoricalDataset:
    dataset_id: str
    filename: str
    symbol: str
    points: tuple[HistoricalPoint, ...]

    @property
    def start(self) -> str: return self.points[0].timestamp

    @property
    def end(self) -> str: return self.points[-1].timestamp


def _number(value: str) -> Optional[float]:
    cleaned = re.sub(r"[^0-9.+-]", "", (value or "").strip())
    if not cleaned or cleaned in {".", "+", "-"}:
        return None
    try:
        result = float(cleaned)
    except ValueError:
        return None
    return result if result > 0 else None


def _timestamp(value: str) -> Optional[str]:
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime((value or "").strip(), fmt).isoformat()
        except ValueError:
            pass
    return None


def parse_nse_csv(text: str, *, filename: str = "historical.csv", dataset_id: str = "") -> HistoricalDataset:
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))
    if not rows or len(rows[0]) < 2:
        raise ValueError("CSV must contain a header and at least one data column")
    headers = [h.strip().lower() for h in rows[0]]
    date_index = next((i for i, h in enumerate(headers) if h in {"date", "datetime", "timestamp"}), 0)
    preferred = [
        i
        for i, h in enumerate(headers)
        if h in {"close", "ltp", "vwap"}
        or h.endswith(" ltp")
        or h.endswith(" close")
        and "prev" not in h
    ]
    candidates = preferred + [i for i in range(len(headers)) if i != date_index and i not in preferred]
    points: list[HistoricalPoint] = []
    for row in rows[1:]:
        if len(row) <= date_index:
            continue
        stamp = _timestamp(row[date_index])
        if not stamp:
            continue
        price = None
        for i in candidates:
            if i < len(row):
                price = _number(row[i])
                if price is not None:
                    break
        if price is not None:
            points.append(HistoricalPoint(stamp, price))
    if not points:
        raise ValueError("No usable timestamp/price rows found. Expected Date/DateTime plus price data.")
    deduped = {point.timestamp: point for point in points}
    ordered = tuple(deduped.values())
    if len(ordered) < 2:
        raise ValueError("Historical replay needs at least two usable rows")
    filename_upper = filename.upper()
    symbol_match = re.search(r"\bRELIANCE\b", filename_upper)
    if symbol_match:
        symbol = "RELIANCE"
    else:
        name_match = re.search(r"(?:QUOTE|EQUITY)[-_ ]+(?:[A-Z]+[-_ ]+)*([A-Z]{2,})", filename_upper)
        symbol = name_match.group(1).rstrip("-_ ") if name_match else "IMPORTED"
    return HistoricalDataset(dataset_id, filename, symbol, ordered)
