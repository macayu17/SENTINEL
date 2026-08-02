"""Offline FI-2010 mid-price direction benchmark helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np


HORIZON_EVENTS = (10, 20, 30, 50, 100)


def load_fi2010_file(path: Path, *, horizon_events: int = 10) -> tuple[np.ndarray, np.ndarray]:
    """Load one FI-2010 fold as samples by features and zero-based labels."""
    if horizon_events not in HORIZON_EVENTS:
        raise ValueError(f"Unsupported FI-2010 horizon: {horizon_events}.")

    path = Path(path)
    if path.suffix.lower() == ".csv":
        raw = np.genfromtxt(path, delimiter=",", skip_header=1)
        if raw.ndim == 2 and raw.shape[1] in (46, 150):
            raw = raw[:, 1:]
    else:
        raw = np.loadtxt(path)
    if raw.ndim != 2:
        raise ValueError("FI-2010 data must be a two-dimensional matrix.")
    if raw.shape[0] in (45, 149):
        raw = raw.T
    if raw.shape[1] not in (45, 149):
        raise ValueError("FI-2010 data must contain features plus five label columns.")

    label_column = raw.shape[1] - 5 + HORIZON_EVENTS.index(horizon_events)
    features = np.asarray(raw[:, :raw.shape[1] - 5], dtype=np.float32)
    labels = np.asarray(raw[:, label_column] - 1, dtype=np.int8)
    if not np.isin(labels, (0, 1, 2)).all():
        raise ValueError("FI-2010 labels must be encoded as 1, 2, or 3.")
    return features, labels
