from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import callback

from custom_components.trv_scheduler.api import ws_get, ws_replace
from custom_components.trv_scheduler.const import DOMAIN
from custom_components.trv_scheduler.manager import ScheduleManager
from custom_components.trv_scheduler.model import Occurrence, TemperatureLimits
from custom_components.trv_scheduler.repository import ScheduleRepository

NOW = datetime(2026, 10, 17, 6, tzinfo=UTC)


@pytest.fixture
async def manager(hass, storage, rows):
    hass.states.async_set(
        "climate.trv2",
        "heat",
        {
            "min_temp": 4,
            "max_temp": 30,
            "target_temp_step": 0.5,
            "temperature": 19,
        },
    )
    hass.states.async_set("input_boolean.gate", "on")
    repo = ScheduleRepository(storage)
    await repo.async_load()
    await repo.async_replace(
        expected_revision=0, enabled=True, rows=rows, limits=TemperatureLimits(4, 30, 0.5)
    )
    obj = ScheduleManager(
        hass,
        {
            "climate_entity": "climate.trv2",
            "gate_entity": "input_boolean.gate",
        },
        repo,
    )
    hass.data[DOMAIN] = {"climate.trv2": obj}
    obj.start()
    yield obj
    await obj.stop()


def connection(allowed=True):
    return SimpleNamespace(
        user=SimpleNamespace(
            is_active=True, permissions=SimpleNamespace(check_entity=Mock(return_value=allowed))
        ),
        send_error=Mock(),
        send_result=Mock(),
    )


async def fire(manager):
    point = Occurrence(manager.repository.schedule.rows[0], NOW)
    with patch("custom_components.trv_scheduler.manager.dt_util.utcnow", return_value=NOW):
        await manager._execute(point, manager.repository.schedule.revision)


async def test_execution_uses_real_ha_service_dispatch(hass, manager):
    calls = []

    @callback
    def handle(call):
        calls.append(call.data)

    hass.services.async_register("climate", "set_temperature", handle)
    await fire(manager)
    assert calls == [{"entity_id": "climate.trv2", "temperature": 17}]
    assert manager.last_result["status"] == "sent"


@pytest.mark.parametrize("gate", ["off", "unknown", "unavailable", None])
async def test_gate_blocks_calls(hass, manager, gate):
    if gate is None:
        hass.states.async_remove("input_boolean.gate")
    else:
        hass.states.async_set("input_boolean.gate", gate)
    with patch.object(type(hass.services), "async_call", new=AsyncMock()) as service:
        await fire(manager)
        service.assert_not_awaited()
    assert manager.last_result["status"] == "blocked"


async def test_optional_setter_script_receives_only_configured_target(hass, manager):
    manager.config["setter_script"] = "script.trv_sollwert_zuverlaessig_setzen"
    with patch.object(type(hass.services), "async_call", new=AsyncMock()) as service:
        await fire(manager)
        service.assert_awaited_once_with(
            "script",
            "trv_sollwert_zuverlaessig_setzen",
            {"climate_entity": "climate.trv2", "temperature": 17},
            blocking=True,
        )


async def test_offline_device_does_not_receive_command(hass, manager):
    hass.states.async_set("climate.trv2", "unavailable")
    with patch.object(type(hass.services), "async_call", new=AsyncMock()) as service:
        await fire(manager)
        service.assert_not_awaited()
    assert manager.last_result["status"] == "failed"


async def test_old_revision_does_not_execute(hass, manager):
    with patch.object(type(hass.services), "async_call", new=AsyncMock()) as service:
        await manager._execute(Occurrence(manager.repository.schedule.rows[0], NOW), 0)
        service.assert_not_awaited()


async def test_start_and_edit_do_not_change_manual_temperature(hass, manager):
    with patch.object(type(hass.services), "async_call", new=AsyncMock()) as service:
        manager.start()
        manager.reschedule()
        await hass.async_block_till_done()
        service.assert_not_awaited()


async def test_late_timer_not_replayed(hass, manager):
    point = Occurrence(manager.repository.schedule.rows[0], NOW - timedelta(minutes=5))
    with patch("custom_components.trv_scheduler.manager.dt_util.utcnow", return_value=NOW):
        await manager._execute(point, 1)
    assert manager.last_result["status"] == "missed"


async def test_ws_read_requires_entity_permission(hass, manager):
    conn = connection(False)
    ws_get(hass, conn, {"id": 1, "entity_id": "climate.trv2"})
    assert conn.send_error.call_args.args[1] == "unauthorized"
    conn.send_result.assert_not_called()


async def test_ws_write_rejects_permission_and_stale_revision(hass, manager, rows):
    msg = {
        "id": 2,
        "entity_id": "climate.trv2",
        "expected_revision": 0,
        "enabled": True,
        "rows": rows,
    }
    conn = connection(False)
    await ws_replace.__wrapped__(hass, conn, msg)
    assert conn.send_error.call_args.args[1] == "unauthorized"
    conn = connection()
    await ws_replace.__wrapped__(hass, conn, msg)
    assert conn.send_error.call_args.args[1] == "revision_conflict"
    assert manager.repository.schedule.revision == 1


async def test_ws_toggle_is_saved_and_reschedules(hass, manager, rows):
    rows[1]["enabled"] = False
    conn = connection()
    await ws_replace.__wrapped__(
        hass,
        conn,
        {
            "id": 3,
            "entity_id": "climate.trv2",
            "expected_revision": 1,
            "enabled": True,
            "rows": rows,
        },
    )
    conn.send_error.assert_not_called()
    result = conn.send_result.call_args.args[1]
    assert result["schedule"]["rows"][0]["enabled"] is False
    assert result["schedule"]["revision"] == 2


async def test_timer_dispatches_once_and_schedules_next_point(hass, manager):
    scheduled = []

    def register(_hass, action, at):
        scheduled.append((action, at))
        return Mock()

    with (
        patch("custom_components.trv_scheduler.manager.async_track_point_in_utc_time", register),
        patch("custom_components.trv_scheduler.manager.dt_util.utcnow") as clock,
        patch.object(type(hass.services), "async_call", new=AsyncMock()) as service,
    ):
        clock.return_value = NOW - timedelta(seconds=1)
        manager.reschedule()
        callback_at_due, at = scheduled.pop()
        assert at == NOW
        clock.return_value = NOW
        callback_at_due(NOW)
        await hass.async_block_till_done()
        service.assert_awaited_once()
        assert scheduled[0][1] == datetime(2026, 10, 17, 15, 30, tzinfo=UTC)


async def test_queued_timer_cannot_fire_after_row_disabled(hass, manager, rows):
    scheduled = []

    def register(_hass, action, at):
        scheduled.append(action)
        return Mock()

    with (
        patch("custom_components.trv_scheduler.manager.async_track_point_in_utc_time", register),
        patch("custom_components.trv_scheduler.manager.dt_util.utcnow") as clock,
        patch.object(type(hass.services), "async_call", new=AsyncMock()) as service,
    ):
        clock.return_value = NOW - timedelta(seconds=1)
        manager.reschedule()
        old_callback = scheduled.pop()
        rows[1]["enabled"] = False
        await manager.repository.async_replace(
            expected_revision=1, enabled=True, rows=rows, limits=manager.limits()
        )
        manager.reschedule()
        clock.return_value = NOW
        next_timer = manager._cancel_timer
        old_callback(NOW)
        await hass.async_block_till_done()
        service.assert_not_awaited()
        assert manager._cancel_timer is next_timer


async def test_stop_prevents_future_commands(hass, manager):
    await manager.stop()
    with patch.object(type(hass.services), "async_call", new=AsyncMock()) as service:
        await fire(manager)
        service.assert_not_awaited()


async def test_lock_plan_cannot_activate_until_adapter_is_available(hass, manager, rows):
    rows[0]["locked"] = True
    conn = connection()
    await ws_replace.__wrapped__(
        hass,
        conn,
        {
            "id": 4,
            "entity_id": "climate.trv2",
            "expected_revision": 1,
            "enabled": True,
            "rows": rows,
        },
    )
    assert conn.send_error.call_args.args[1] == "invalid_schedule"
    assert manager.repository.schedule.revision == 1
    assert manager.snapshot()["lock_supported"] is False


async def test_lock_plan_can_be_saved_as_disabled_draft(hass, manager, rows):
    rows[0]["locked"] = True
    conn = connection()
    await ws_replace.__wrapped__(
        hass,
        conn,
        {
            "id": 5,
            "entity_id": "climate.trv2",
            "expected_revision": 1,
            "enabled": False,
            "rows": rows,
        },
    )
    conn.send_error.assert_not_called()
    assert manager.repository.schedule.rows[1].locked is True
    assert manager.repository.schedule.enabled is False


async def test_runtime_does_not_silently_ignore_missing_lock_adapter(hass, manager):
    from dataclasses import replace

    locked = replace(manager.repository.schedule.rows[0], locked=True)
    with (
        patch("custom_components.trv_scheduler.manager.dt_util.utcnow", return_value=NOW),
        patch.object(type(hass.services), "async_call", new=AsyncMock()) as service,
    ):
        await manager._execute(Occurrence(locked, NOW), 1)
        service.assert_not_awaited()
    assert manager.last_result["status"] == "failed"
