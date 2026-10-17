import asyncio
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from custom_components.trv_scheduler.device_lock import DeviceLock
from custom_components.trv_scheduler.gateway import GatewayError, ShellyGateway
from custom_components.trv_scheduler.manager import ScheduleManager
from custom_components.trv_scheduler.model import TemperatureLimits
from custom_components.trv_scheduler.repository import ScheduleRepository


async def test_gateway_minimal_patch_and_fresh_readback():
    calls = []

    async def respond(request):
        import json

        payload = json.loads(request.content)
        calls.append(payload)
        return httpx.Response(
            200, json={"id": 1, "result": None if len(calls) == 1 else {"ui": {"lock": True}}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        gateway = ShellyGateway(client, lambda: {"host": "gateway.test"}, 201, asyncio.Lock())
        assert await gateway.async_set_lock(True)
    assert calls[0]["params"] == {
        "id": 201,
        "method": "Sys.SetConfig",
        "params": {"config": {"ui": {"lock": True}}},
    }
    assert calls[1]["params"]["method"] == "Sys.GetConfig"


@pytest.mark.parametrize("result", [None, {}, {"ui": {"lock": "false"}}, {"ui": {"lock": False}}])
async def test_gateway_never_claims_unconfirmed_lock(result):
    count = 0

    async def respond(request):
        nonlocal count
        count += 1
        return httpx.Response(200, json={"id": 1, "result": None if count == 1 else result})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        gateway = ShellyGateway(client, lambda: {"host": "gateway.test"}, 200, asyncio.Lock())
        with pytest.raises(GatewayError):
            await gateway.async_set_lock(True)


async def test_gateway_digest_authentication():
    headers = []

    def respond(request):
        headers.append(request.headers.get("authorization"))
        if not headers[-1]:
            return httpx.Response(
                401,
                headers={
                    "WWW-Authenticate": (
                        'Digest realm="test", nonce="abc", algorithm=SHA-256, qop="auth"'
                    )
                },
            )
        return httpx.Response(200, json={"id": 1, "result": {"ui": {"lock": False}}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        gateway = ShellyGateway(
            client,
            lambda: {"host": "gateway.test", "username": "admin", "password": "test-only"},
            200,
            asyncio.Lock(),
        )
        assert await gateway.async_read_lock() is False
    assert headers[1].startswith("Digest ")
    assert "test-only" not in headers[1]


async def test_lock_ownership_persists_before_failed_send(storage):
    gateway = AsyncMock()
    gateway.async_set_lock.side_effect = GatewayError("offline")
    lock = DeviceLock(gateway, storage)
    await lock.async_load()
    with pytest.raises(GatewayError):
        await lock.async_apply(True)
    assert storage.data == {"owned": True}
    assert lock.snapshot()["locked"] is None
    restarted = DeviceLock(gateway, storage)
    await restarted.async_load()
    assert restarted.owned
    gateway.async_set_lock.side_effect = None
    gateway.async_set_lock.return_value = False
    await restarted.async_apply(False)
    assert storage.data == {"owned": False}


async def test_storage_failure_prevents_locking(storage):
    gateway = AsyncMock()
    lock = DeviceLock(gateway, storage)
    storage.fail = True
    with pytest.raises(OSError):
        await lock.async_apply(True)
    gateway.async_set_lock.assert_not_awaited()


@pytest.fixture
async def controlled(hass, storage, rows):
    from conftest import MemoryStorage

    repo = ScheduleRepository(storage)
    await repo.async_load()
    await repo.async_replace(
        expected_revision=0, enabled=True, rows=rows, limits=TemperatureLimits(4, 30, 0.5)
    )
    gateway = AsyncMock()
    gateway.async_set_lock.side_effect = lambda value: value
    device_lock = DeviceLock(gateway, MemoryStorage())
    await device_lock.async_load()
    hass.states.async_set(
        "climate.test", "heat", {"min_temp": 4, "max_temp": 30, "target_temp_step": 0.5}
    )
    hass.states.async_set("input_boolean.gate", "on")
    manager = ScheduleManager(
        hass,
        {"climate_entity": "climate.test", "gate_entity": "input_boolean.gate"},
        repo,
        device_lock,
    )
    manager.start()
    yield manager
    await manager.stop()


async def test_disable_plan_releases_owned_lock(controlled):
    await controlled.device_lock.async_apply(True)
    await controlled.async_replace(
        expected_revision=1, enabled=False, rows=[], limits=controlled.limits()
    )
    assert not controlled.device_lock.owned
    assert controlled.device_lock.locked is False


async def test_failed_unlock_keeps_plan_disabled_and_queues_retry(controlled):
    await controlled.device_lock.async_apply(True)
    controlled.device_lock.gateway.async_set_lock.side_effect = GatewayError("offline")
    await controlled.async_replace(
        expected_revision=1, enabled=False, rows=[], limits=controlled.limits()
    )
    assert not controlled.repository.schedule.enabled
    assert controlled.device_lock.owned
    assert controlled._cancel_retry is not None
    assert controlled.snapshot()["device_lock"]["error"]


async def test_gate_off_releases_lock(hass, controlled):
    await controlled.device_lock.async_apply(True)
    hass.states.async_set("input_boolean.gate", "off")
    await hass.async_block_till_done()
    assert controlled.device_lock.locked is False


async def test_manual_unlock_does_not_disable_schedule(controlled):
    await controlled.device_lock.async_apply(True)
    await controlled.async_unlock()
    assert controlled.repository.schedule.enabled
    assert not controlled.device_lock.locked


async def test_scheduled_lock_applies_after_temperature(hass, controlled):
    from dataclasses import replace

    from homeassistant.util import dt as dt_util

    from custom_components.trv_scheduler.model import Occurrence

    row = replace(controlled.repository.schedule.rows[0], locked=True)
    with patch.object(type(hass.services), "async_call", new=AsyncMock()) as service:
        await controlled._execute(Occurrence(row, dt_util.utcnow()), 1)
        service.assert_awaited_once()
    assert controlled.device_lock.locked
    assert controlled.last_result["status"] == "sent"


async def test_failed_temperature_does_not_prevent_scheduled_unlock(hass, controlled):
    from homeassistant.exceptions import HomeAssistantError
    from homeassistant.util import dt as dt_util

    from custom_components.trv_scheduler.model import Occurrence

    await controlled.device_lock.async_apply(True)
    with patch.object(
        type(hass.services), "async_call", new=AsyncMock(side_effect=HomeAssistantError("offline"))
    ):
        await controlled._execute(
            Occurrence(controlled.repository.schedule.rows[0], dt_util.utcnow()), 1
        )
    assert controlled.device_lock.locked is False
    assert controlled.last_result["status"] == "failed"


async def test_unload_waits_for_inflight_lock_then_releases(controlled):
    started = asyncio.Event()
    finish = asyncio.Event()

    async def inflight():
        async with controlled._operation_lock:
            started.set()
            await finish.wait()
            await controlled.device_lock.async_apply(True)

    worker = asyncio.create_task(inflight())
    await started.wait()
    stopping = asyncio.create_task(controlled.stop(release=True))
    await asyncio.sleep(0)
    assert not stopping.done()
    finish.set()
    await asyncio.gather(worker, stopping)
    assert controlled.device_lock.locked is False
    assert not controlled.device_lock.owned
    assert controlled._stopped
