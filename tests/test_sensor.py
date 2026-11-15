"""Tests for the iDevices HomeKit Power sensors."""

from __future__ import annotations

from datetime import timedelta

from aiohomekit.exceptions import AccessoryDisconnectedError
from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.idevices_power.hkc import device_identifier

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from .conftest import (
    ACCESSORIES,
    ENERGY_IID,
    HKID,
    POWER_IID,
    FakeConnection,
    add_paired_device,
)

POWER = "sensor.outdoor_switch_1_power"
ENERGY = "sensor.outdoor_switch_1_energy"
HKID_2 = "11:22:33:44:55:66"
POWER_2 = "sensor.outdoor_switch_2_power"
ENERGY_2 = "sensor.outdoor_switch_2_energy"

# A HomeKit device without the iDevices power service.
OTHER_ACCESSORIES = [{"aid": 1, "services": [ACCESSORIES[0]["services"][0]]}]


async def _setup(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    # Polls run as background tasks.
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_sensors(
    hass: HomeAssistant, connection: FakeConnection, config_entry: MockConfigEntry
) -> None:
    """Readings are converted and attached to the HomeKit device."""
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    power = hass.states.get(POWER)
    assert float(power.state) == pytest.approx(452.3)
    assert power.attributes["unit_of_measurement"] == "W"
    assert power.attributes["state_class"] == "measurement"

    energy = hass.states.get(ENERGY)
    assert float(energy.state) == pytest.approx(12345000000.0 / 3.6e9)
    assert energy.attributes["unit_of_measurement"] == "kWh"
    assert energy.attributes["state_class"] == "total_increasing"

    device = dr.async_get(hass).async_get_device_by_identifier(
        device_identifier(HKID, 1), connection.config_entry.entry_id
    )
    entities = er.async_get(hass)
    assert entities.async_get(POWER).device_id == device.id
    assert entities.async_get(ENERGY).device_id == device.id
    assert len(dr.async_get(hass).devices) == 1

    connection.get_characteristics.assert_awaited_once_with({POWER_IID, ENERGY_IID})


async def test_switch_paired_later(
    hass: HomeAssistant,
    connection: FakeConnection,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A switch paired after setup gets sensors on the next poll."""
    await _setup(hass, config_entry)
    assert hass.states.get(POWER_2) is None

    second = add_paired_device(hass, HKID_2, "Outdoor Switch 2")
    second.get_characteristics.return_value = {
        POWER_IID: {"value": 7000},
        ENERGY_IID: {"value": 3600000000.0},
    }
    await _poll(hass, freezer)

    assert float(hass.states.get(POWER_2).state) == pytest.approx(7.0)
    assert float(hass.states.get(ENERGY_2).state) == pytest.approx(1.0)
    assert float(hass.states.get(POWER).state) == pytest.approx(452.3)


async def test_one_switch_unreachable(
    hass: HomeAssistant,
    connection: FakeConnection,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Only the switch that can't be read goes unavailable, until it is back."""
    second = add_paired_device(hass, HKID_2, "Outdoor Switch 2")
    await _setup(hass, config_entry)

    second.get_characteristics.side_effect = AccessoryDisconnectedError("gone")
    await _poll(hass, freezer)
    assert hass.states.get(POWER_2).state == STATE_UNAVAILABLE
    assert hass.states.get(ENERGY_2).state == STATE_UNAVAILABLE
    assert float(hass.states.get(POWER).state) == pytest.approx(452.3)

    second.get_characteristics.side_effect = None
    await _poll(hass, freezer)
    assert float(hass.states.get(POWER_2).state) == pytest.approx(452.3)


async def test_missing_value(
    hass: HomeAssistant, connection: FakeConnection, config_entry: MockConfigEntry
) -> None:
    """A characteristic read that returns an error status is unavailable."""
    connection.get_characteristics.return_value = {
        POWER_IID: {"value": 5000},
        ENERGY_IID: {"status": -70402, "description": "Unable to communicate"},
    }
    await _setup(hass, config_entry)

    assert float(hass.states.get(POWER).state) == pytest.approx(5.0)
    assert hass.states.get(ENERGY).state == STATE_UNAVAILABLE


async def test_ignores_other_devices(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Devices without the power service, or not connected, are left alone."""
    other = add_paired_device(hass, HKID_2, "Light", OTHER_ACCESSORIES)
    offline = add_paired_device(
        hass, HKID, "Offline", state=ConfigEntryState.SETUP_RETRY
    )
    await _setup(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.async_entity_ids("sensor") == []
    other.get_characteristics.assert_not_awaited()
    offline.get_characteristics.assert_not_awaited()


async def test_homekit_reloaded(
    hass: HomeAssistant,
    connection: FakeConnection,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A new connection object is picked up after homekit_controller reloads."""
    await _setup(hass, config_entry)

    new_connection = FakeConnection(connection.config_entry, HKID, ACCESSORIES)
    new_connection.get_characteristics.return_value = {
        POWER_IID: {"value": 2000},
        ENERGY_IID: {"value": 12345000000.0},
    }
    hass.data["homekit_controller-devices"][HKID] = new_connection
    await _poll(hass, freezer)

    assert float(hass.states.get(POWER).state) == pytest.approx(2.0)


async def test_switch_removed(
    hass: HomeAssistant,
    connection: FakeConnection,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Sensors are deleted with the switch, and come back if it is re-paired."""
    await _setup(hass, config_entry)
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
    device = devices.async_get_device_by_identifier(
        device_identifier(HKID, 1), connection.config_entry.entry_id
    )

    # Deleting the HomeKit entry unloads its connection and removes its device.
    await hass.config_entries.async_remove(connection.config_entry.entry_id)
    await hass.async_block_till_done()
    assert devices.async_get(device.id) is None
    assert entities.async_get(POWER) is None
    assert entities.async_get(ENERGY) is None
    assert hass.states.get(POWER) is None

    await _poll(hass, freezer)
    assert entities.async_get(POWER) is None

    add_paired_device(hass, HKID, "Outdoor Switch 1")
    await _poll(hass, freezer)
    assert float(hass.states.get(POWER).state) == pytest.approx(452.3)
    assert entities.async_get(POWER).device_id is not None
