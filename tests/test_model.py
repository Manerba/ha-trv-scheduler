from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from custom_components.trv_scheduler.model import (
    InvalidSchedule,
    Schedule,
    TemperatureLimits,
    next_occurrence,
)

BERLIN = ZoneInfo("Europe/Berlin")
LIMITS = TemperatureLimits(4, 30, 0.5)


def plan(rows, enabled=True):
    return Schedule.parse({"revision": 1, "enabled": enabled, "rows": rows}, LIMITS)


def test_sort_and_roundtrip(rows):
    schedule = plan(rows)
    assert [r.id for r in schedule.rows] == ["morning", "evening"]
    assert Schedule.parse(schedule.to_dict()) == schedule


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "22", None, -1, 31, 20.2])
def test_reject_bad_temperature(rows, value):
    rows[0]["temperature"] = value
    with pytest.raises(InvalidSchedule):
        plan(rows)


@pytest.mark.parametrize("value", ["8:00", "24:00", "12:60", "08:00:00", None, "08:00\n"])
def test_reject_bad_time(rows, value):
    rows[0]["time"] = value
    with pytest.raises(InvalidSchedule):
        plan(rows)


@pytest.mark.parametrize("field", ["id", "time"])
def test_reject_duplicates(rows, field):
    rows[1][field] = rows[0][field]
    with pytest.raises(InvalidSchedule):
        plan(rows)


def test_disabled_row_keeps_values_and_is_skipped(rows):
    rows[1]["enabled"] = False
    schedule = plan(rows)
    assert schedule.rows[0].temperature == 17
    assert schedule.rows[0].time == "08:00"
    point = next_occurrence(schedule, datetime(2026, 10, 17, 5, tzinfo=UTC), BERLIN)
    assert point.row.id == "evening"


def test_all_rows_disabled_and_empty_plan_have_no_next_point(rows):
    for row in rows:
        row["enabled"] = False
    now = datetime(2026, 10, 17, tzinfo=UTC)
    assert next_occurrence(plan(rows), now, BERLIN) is None
    assert next_occurrence(plan([]), now, BERLIN) is None
    assert next_occurrence(plan(rows, enabled=False), now, BERLIN) is None


def test_next_is_strictly_future(rows):
    point = next_occurrence(plan(rows), datetime(2026, 10, 17, 6, tzinfo=UTC), BERLIN)
    assert point.row.id == "evening"
    assert point.at == datetime(2026, 10, 17, 15, 30, tzinfo=UTC)


def test_midnight_wrap(rows):
    point = next_occurrence(plan(rows), datetime(2026, 10, 17, 20, tzinfo=UTC), BERLIN)
    assert point.at == datetime(2026, 10, 18, 6, tzinfo=UTC)


def test_spring_missing_hour_is_skipped():
    schedule = plan([{"id": "x", "time": "02:30", "temperature": 20, "enabled": True}])
    point = next_occurrence(schedule, datetime(2026, 3, 29, 0, tzinfo=UTC), BERLIN)
    assert point.at == datetime(2026, 3, 30, 0, 30, tzinfo=UTC)


def test_autumn_overlap_fires_only_first_time():
    schedule = plan([{"id": "x", "time": "02:30", "temperature": 20, "enabled": True}])
    first = next_occurrence(schedule, datetime(2026, 10, 25, 0, tzinfo=UTC), BERLIN)
    assert first.at == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    second = next_occurrence(schedule, first.at, BERLIN)
    assert second.at == datetime(2026, 10, 26, 1, 30, tzinfo=UTC)


@pytest.mark.parametrize("enabled", [0, 1, "on", None])
def test_toggle_requires_boolean(rows, enabled):
    rows[0]["enabled"] = enabled
    with pytest.raises(InvalidSchedule):
        plan(rows)


def test_unknown_fields_rejected(rows):
    rows[0]["service"] = "script.other"
    with pytest.raises(InvalidSchedule):
        plan(rows)
