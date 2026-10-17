import asyncio
from unittest.mock import patch

import pytest
from homeassistant.util.file import WriteError

from custom_components.trv_scheduler.model import (
    InvalidSchedule,
    RevisionConflict,
    TemperatureLimits,
)
from custom_components.trv_scheduler.repository import ScheduleRepository
from custom_components.trv_scheduler.storage import VerifiedStore

LIMITS = TemperatureLimits(4, 30, 0.5)


async def replace(repo, rows, revision=0):
    return await repo.async_replace(
        expected_revision=revision, enabled=True, rows=rows, limits=LIMITS
    )


async def test_new_repository_is_disabled(storage):
    repo = ScheduleRepository(storage)
    await repo.async_load()
    assert repo.schedule.to_dict() == {"revision": 0, "enabled": False, "rows": []}


async def test_save_and_reload_retains_row_toggle(storage, rows):
    rows[0]["enabled"] = False
    repo = ScheduleRepository(storage)
    await repo.async_load()
    saved = await replace(repo, rows)
    restarted = ScheduleRepository(storage)
    await restarted.async_load()
    assert restarted.schedule == saved
    assert restarted.schedule.rows[1].enabled is False
    assert saved.revision == 1


async def test_concurrent_edit_has_one_winner(storage, rows):
    repo = ScheduleRepository(storage)
    await repo.async_load()
    results = await asyncio.gather(replace(repo, rows), replace(repo, rows), return_exceptions=True)
    assert sum(isinstance(r, RevisionConflict) for r in results) == 1
    assert repo.schedule.revision == 1


async def test_failed_save_does_not_publish_or_increment(storage, rows):
    repo = ScheduleRepository(storage)
    await repo.async_load()
    original = await replace(repo, rows)
    storage.fail = True
    with pytest.raises(OSError):
        await replace(repo, [], revision=1)
    assert repo.schedule == original
    assert storage.data == original.to_dict()


async def test_invalid_saved_data_is_not_silently_reset(storage):
    storage.data = {"revision": "bad", "enabled": True, "rows": []}
    repo = ScheduleRepository(storage)
    with pytest.raises(InvalidSchedule):
        await repo.async_load()
    assert storage.data["revision"] == "bad"


async def test_actual_ha_store_roundtrip(hass, rows):
    store = VerifiedStore(hass, "trv_scheduler.test")
    repo = ScheduleRepository(store)
    await repo.async_load()
    await replace(repo, rows)
    fresh = ScheduleRepository(VerifiedStore(hass, "trv_scheduler.test"))
    await fresh.async_load()
    assert fresh.schedule == repo.schedule


async def test_ha_swallowed_write_failure_does_not_publish(hass, rows):
    repo = ScheduleRepository(VerifiedStore(hass, "trv_scheduler.test"))
    await repo.async_load()
    before = await replace(repo, rows)
    with patch(
        "homeassistant.helpers.storage.json_helper.save_json", side_effect=WriteError("full")
    ):
        with pytest.raises(OSError, match="could not be verified"):
            await replace(repo, [], revision=1)
    assert repo.schedule == before


async def test_can_disable_row_offline_but_cannot_reenable(storage, rows):
    repo = ScheduleRepository(storage)
    await repo.async_load()
    await replace(repo, rows)
    rows[0]["enabled"] = False
    await repo.async_replace(expected_revision=1, enabled=True, rows=rows, limits=None)
    rows[0]["enabled"] = True
    with pytest.raises(InvalidSchedule, match="nicht erreichbar"):
        await repo.async_replace(expected_revision=2, enabled=True, rows=rows, limits=None)
    assert repo.schedule.revision == 2
