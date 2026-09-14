"""Interview slot store + conflict checking.

v1 uses a DB-backed calendar (per the proposal): a seeded set of demo slots is
conflict-checked against existing ``interviews`` records so the agent never
double-books. Google Calendar API can be swapped in behind the same interface
later (see §17 / §18 of the proposal).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

from app.services.store import Store

SLOT_MINUTES = 60

# Seeded demo slots: (weekday, hour, minute). Monday=0 … Sunday=6.
WEEKDAY_SLOTS: list[tuple[int, int, int]] = [
    (0, 10, 0),   # Mon 10:00
    (0, 14, 0),   # Mon 14:00
    (1, 11, 30),  # Tue 11:30
    (2, 9, 0),    # Wed 09:00
]

_WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _next_occurrence(weekday: int, hour: int, minute: int, now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now()
    days_ahead = (weekday - now.weekday()) % 7
    if days_ahead == 0:
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            days_ahead = 7
    target = (now + timedelta(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target


def seed_slots(now: Optional[datetime] = None) -> list[dict[str, Any]]:
    """Materialise the seeded demo slots onto the upcoming week's dates."""
    slots = []
    for weekday, hour, minute in WEEKDAY_SLOTS:
        start = _next_occurrence(weekday, hour, minute, now)
        end = start + timedelta(minutes=SLOT_MINUTES)
        slots.append(
            {
                "weekday": _WEEKDAY_NAMES[weekday],
                "slot_start": start.isoformat(),
                "slot_end": end.isoformat(),
                "label": f"{_WEEKDAY_NAMES[weekday]} {start.strftime('%H:%M')}",
            }
        )
    return slots


def _overlaps(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    return a_start < b_end and b_start < a_end


def list_available_slots(store: Store) -> list[dict[str, Any]]:
    """Return seed slots not already taken by a scheduled interview."""
    interviews = store.list_interviews()
    taken = [(i.get("slot_start"), i.get("slot_end")) for i in interviews if i.get("status") != "cancelled"]
    available = []
    for slot in seed_slots():
        if not any(
            _overlaps(slot["slot_start"], slot["slot_end"], s, e) for s, e in taken if s and e
        ):
            available.append(slot)
    return available


def find_slot(store: Store, slot_start: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Pick an available slot — either a specific one or the first free one."""
    available = list_available_slots(store)
    if not available:
        return None
    if slot_start:
        for s in available:
            if s["slot_start"] == slot_start:
                return s
        return None
    return available[0]
