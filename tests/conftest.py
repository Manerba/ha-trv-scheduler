from copy import deepcopy

import pytest
from homeassistant.core import HomeAssistant


class MemoryStorage:
    def __init__(self, data=None):
        self.data = deepcopy(data)
        self.fail = False

    async def async_load(self):
        return deepcopy(self.data)

    async def async_save(self, data):
        if self.fail:
            raise OSError("Disk full")
        self.data = deepcopy(data)


@pytest.fixture
def storage():
    return MemoryStorage()


@pytest.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    await instance.config.async_set_time_zone("Europe/Berlin")
    yield instance
    await instance.async_stop(force=True)


@pytest.fixture
def rows():
    return [
        {"id": "evening", "time": "17:30", "temperature": 22, "enabled": True},
        {"id": "morning", "time": "08:00", "temperature": 17, "enabled": True},
    ]
