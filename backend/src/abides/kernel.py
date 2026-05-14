"""ABIDES-style discrete event kernel."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, List


class EventType(Enum):
    WAKEUP = auto()
    MESSAGE = auto()


@dataclass(order=True)
class Event:
    timestamp: float
    event_id: int
    event_type: EventType = field(compare=False)
    callback: Callable[[Any], None] = field(compare=False)
    data: Any = field(compare=False, default=None)


class EventKernel:
    """Priority-queue event scheduler."""

    def __init__(self) -> None:
        self.queue: List[Event] = []
        self.current_time: float = 0.0
        self._event_counter: int = 0

    def schedule_in(self, delay: float, event_type: EventType, callback: Callable[[Any], None], data: Any = None) -> int:
        """Schedule an event delay seconds in the future."""
        self._event_counter += 1
        trigger_time = self.current_time + max(0.0, float(delay))
        event = Event(trigger_time, self._event_counter, event_type, callback, data)
        heapq.heappush(self.queue, event)
        return self._event_counter

    def schedule_at(self, timestamp: float, event_type: EventType, callback: Callable[[Any], None], data: Any = None) -> int:
        """Schedule an event at an absolute timestamp."""
        self._event_counter += 1
        event = Event(float(timestamp), self._event_counter, event_type, callback, data)
        heapq.heappush(self.queue, event)
        return self._event_counter

    def run_until(self, target_time: float) -> None:
        """Process events until target_time."""
        target = float(target_time)
        while self.queue and self.queue[0].timestamp <= target:
            event = heapq.heappop(self.queue)
            self.current_time = event.timestamp
            event.callback(event.data)
        self.current_time = max(self.current_time, target)

    def clear(self) -> None:
        """Reset the kernel state."""
        self.queue.clear()
        self.current_time = 0.0
        self._event_counter = 0
