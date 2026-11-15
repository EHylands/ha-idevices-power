"""Fixtures for the iDevices HomeKit Power tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

from aiohomekit.model import Accessories
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.idevices_power.const import CONF_HKID, DOMAIN
from custom_components.idevices_power.hkc import (
    HKC_DOMAIN,
    KNOWN_DEVICES,
    device_identifier,
)

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    mock_integration,
)

HKID = "AA:BB:CC:DD:EE:01"
TITLE = "Outdoor Switch 1"
ON_IID = (1, 11)
POWER_IID = (1, 61)
ENERGY_IID = (1, 62)

# Trimmed entity map of an iDevices Outdoor Switch (IDEV0004).
ACCESSORIES = [
    {
        "aid": 1,
        "services": [
            {
                "iid": 1,
                "type": "0000003E-0000-1000-8000-0026BB765291",
                "characteristics": [
                    {"iid": 2, "type": "00000023-0000-1000-8000-0026BB765291", "format": "string", "perms": ["pr"], "value": TITLE},
                    {"iid": 3, "type": "00000020-0000-1000-8000-0026BB765291", "format": "string", "perms": ["pr"], "value": "iDevices LLC"},
                    {"iid": 4, "type": "00000021-0000-1000-8000-0026BB765291", "format": "string", "perms": ["pr"], "value": "IDEV0004"},
                    {"iid": 5, "type": "00000030-0000-1000-8000-0026BB765291", "format": "string", "perms": ["pr"], "value": "00000000"},
                    {"iid": 6, "type": "00000014-0000-1000-8000-0026BB765291", "format": "bool", "perms": ["pw"]},
                    {"iid": 7, "type": "00000052-0000-1000-8000-0026BB765291", "format": "string", "perms": ["pr"], "value": "1.9.11"},
                ],
            },
            {
                "iid": 10,
                "type": "00000049-0000-1000-8000-0026BB765291",
                "characteristics": [
                    {"iid": 11, "type": "00000025-0000-1000-8000-0026BB765291", "format": "bool", "perms": ["pr", "pw", "ev"], "value": True},
                ],
            },
            {
                "iid": 60,
                "type": "6747C101-FAC9-4D62-ADF4-E764D0A8B39D",
                "characteristics": [
                    {"iid": 61, "type": "6747C102-FAC9-4D62-ADF4-E764D0A8B39D", "format": "int", "perms": ["pr"], "value": 0},
                    {"iid": 62, "type": "6747C103-FAC9-4D62-ADF4-E764D0A8B39D", "format": "float", "perms": ["pr"], "value": 0},
                ],
            },
        ],
    }
]


# A HomeKit device without the iDevices power service.
OTHER_ACCESSORIES = [{"aid": 1, "services": [ACCESSORIES[0]["services"][0]]}]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Enable custom integrations in all tests."""


class FakeConnection:
    """Stands in for homekit_controller's HKDevice."""

    def __init__(
        self,
        config_entry: MockConfigEntry,
        hkid: str,
        accessories: list[dict[str, Any]],
    ) -> None:
        self.config_entry = config_entry
        self.unique_id = hkid
        self.entity_map = Accessories.from_list(accessories)
        self.get_characteristics = AsyncMock(
            return_value={
                POWER_IID: {"value": 452300},
                ENERGY_IID: {"value": 12345000000.0},
            }
        )
        self.subscriptions: dict[tuple[int, int], set[Callable[[], None]]] = {}

    def async_subscribe(
        self, characteristics: set[tuple[int, int]], callback: Callable[[], None]
    ) -> Callable[[], None]:
        """Follow pushed changes, as HKDevice.async_subscribe does."""
        for aid_iid in characteristics:
            self.subscriptions.setdefault(aid_iid, set()).add(callback)

        def unsubscribe() -> None:
            for aid_iid in characteristics:
                self.subscriptions[aid_iid].remove(callback)
                if not self.subscriptions[aid_iid]:
                    del self.subscriptions[aid_iid]

        return unsubscribe

    def push(self, aid_iid: tuple[int, int]) -> None:
        """Deliver a pushed change, as HKDevice.process_new_events does."""
        for callback in set(self.subscriptions.get(aid_iid, ())):
            callback()


def add_paired_device(
    hass: HomeAssistant,
    hkid: str,
    title: str,
    accessories: list[dict[str, Any]] = ACCESSORIES,
    state: ConfigEntryState = ConfigEntryState.LOADED,
) -> FakeConnection:
    """Add a device as homekit_controller would after pairing it."""
    entry = MockConfigEntry(
        domain=HKC_DOMAIN,
        title=title,
        unique_id=hkid.lower(),
        data={"AccessoryPairingID": hkid},
        state=state,
    )
    entry.add_to_hass(hass)
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={device_identifier(hkid, 1)},
        name=title,
    )
    conn = FakeConnection(entry, hkid, accessories)
    hass.data.setdefault(KNOWN_DEVICES, {})[hkid] = conn
    return conn


@pytest.fixture(autouse=True)
def homekit_controller(hass: HomeAssistant) -> None:
    """Stand in for the homekit_controller integration being loaded."""
    mock_integration(hass, MockModule(HKC_DOMAIN))
    hass.config.components.add(HKC_DOMAIN)


@pytest.fixture
def connection(hass: HomeAssistant) -> FakeConnection:
    """The homekit_controller connection for the switch."""
    return add_paired_device(hass, HKID, TITLE)


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """The iDevices HomeKit Power entry for the switch."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title=TITLE,
        unique_id=HKID.lower(),
        data={CONF_HKID: HKID},
    )
    entry.add_to_hass(hass)
    return entry
