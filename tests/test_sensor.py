"""Tests for the iDevices HomeKit Power sensors and entry lifecycle."""

from __future__ import annotations

from datetime import timedelta

from aiohomekit.exceptions import AccessoryDisconnectedError
from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.idevices_power.const import (
    CONF_HKID,
    DOMAIN,
    SWITCH_READ_COUNT,
    SWITCH_READ_INTERVAL,
)
from custom_components.idevices_power.hkc import device_identifier

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from .conftest import (
    ACCESSORIES,
    ENERGY_IID,
    HKID,
    ON_IID,
    POWER_IID,
    TITLE,
    FakeConnection,
    add_paired_device,
)

POWER = "sensor.outdoor_switch_1_power"
ENERGY = "sensor.outdoor_switch_1_energy"
HKID_2 = "11:22:33:44:55:66"


async def _setup(hass: HomeAssistant, config_entry: MockConfigEntry) -> bool:
    result = await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return result


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(seconds=30))
    async_fire_time_changed(hass)
    # Polls run as background tasks.
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_sensors(
    hass: HomeAssistant, connection: FakeConnection, config_entry: MockConfigEntry
) -> None:
    """Readings are converted and attached to the HomeKit device."""
    assert await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED

    power = hass.states.get(POWER)
    assert float(power.state) == pytest.approx(452.3)
    assert power.attributes["unit_of_measurement"] == "W"
    assert power.attributes["state_class"] == "measurement"

    energy = hass.states.get(ENERGY)
    assert float(energy.state) == pytest.approx(12345000000.0 / 3.6e9)
    assert energy.attributes["unit_of_measurement"] == "kWh"
    assert energy.attributes["state_class"] == "total_increasing"

    # Shown without decimals by default; the state keeps full precision.
    entities = er.async_get(hass)
    for entity_id in (POWER, ENERGY):
        options = entities.async_get(entity_id).options["sensor"]
        assert options["suggested_display_precision"] == 0

    devices = dr.async_get(hass)
    device = devices.async_get_device_by_identifier(
        device_identifier(HKID, 1), config_entry.entry_id
    )
    assert device.name == TITLE
    assert device.manufacturer == "iDevices LLC"
    assert device.model == "IDEV0004"
    assert device.sw_version == "1.9.11"
    assert entities.async_get(POWER).device_id == device.id
    assert entities.async_get(ENERGY).device_id == device.id

    # Linked to homekit_controller's device for the same switch.
    linked = devices.async_get_devices(identifiers=device.identifiers)
    assert {d.config_entry_id for d in linked} == {
        config_entry.entry_id,
        connection.config_entry.entry_id,
    }

    connection.get_characteristics.assert_awaited_once_with({POWER_IID, ENERGY_IID})


async def test_sensors_move_to_own_device(
    hass: HomeAssistant, connection: FakeConnection, config_entry: MockConfigEntry
) -> None:
    """Sensors that 0.2.1 put on homekit_controller's device keep their IDs."""
    hkc_device = dr.async_get(hass).async_get_device_by_identifier(
        device_identifier(HKID, 1), connection.config_entry.entry_id
    )
    entities = er.async_get(hass)
    old = entities.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{HKID}_1_61",
        config_entry=config_entry,
        device_id=hkc_device.id,
        suggested_object_id="old_power_sensor",
    )

    assert await _setup(hass, config_entry)

    moved = entities.async_get(old.entity_id)
    assert moved.device_id != hkc_device.id
    assert dr.async_get(hass).async_get(moved.device_id).config_entry_id == (
        config_entry.entry_id
    )
    assert float(hass.states.get(old.entity_id).state) == pytest.approx(452.3)
    # homekit_controller's device is untouched.
    assert dr.async_get(hass).async_get(hkc_device.id) is not None


async def test_polling_and_errors(
    hass: HomeAssistant,
    connection: FakeConnection,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Readings are polled, and go unavailable while the switch can't be read."""
    assert await _setup(hass, config_entry)

    connection.get_characteristics.return_value = {
        POWER_IID: {"value": 1000},
        ENERGY_IID: {"value": 12355000000.0},
    }
    await _poll(hass, freezer)
    assert float(hass.states.get(POWER).state) == pytest.approx(1.0)

    connection.get_characteristics.side_effect = AccessoryDisconnectedError("gone")
    await _poll(hass, freezer)
    assert hass.states.get(POWER).state == STATE_UNAVAILABLE
    assert hass.states.get(ENERGY).state == STATE_UNAVAILABLE

    connection.get_characteristics.side_effect = None
    await _poll(hass, freezer)
    assert float(hass.states.get(POWER).state) == pytest.approx(1.0)


async def test_missing_value(
    hass: HomeAssistant, connection: FakeConnection, config_entry: MockConfigEntry
) -> None:
    """A characteristic read that returns an error status is unavailable."""
    connection.get_characteristics.return_value = {
        POWER_IID: {"value": 5000},
        ENERGY_IID: {"status": -70402, "description": "Unable to communicate"},
    }
    assert await _setup(hass, config_entry)

    assert float(hass.states.get(POWER).state) == pytest.approx(5.0)
    assert hass.states.get(ENERGY).state == STATE_UNAVAILABLE


async def test_homekit_not_loaded(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Setup is retried until homekit_controller has connected."""
    add_paired_device(hass, HKID, TITLE, state=ConfigEntryState.SETUP_RETRY)
    assert not await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_pairing_missing(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """Setup fails without retrying when the switch is no longer paired."""
    assert not await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_homekit_reloaded(
    hass: HomeAssistant,
    connection: FakeConnection,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A new connection object is picked up after homekit_controller reloads."""
    assert await _setup(hass, config_entry)

    new_connection = FakeConnection(connection.config_entry, HKID, ACCESSORIES)
    new_connection.get_characteristics.return_value = {
        POWER_IID: {"value": 2000},
        ENERGY_IID: {"value": 12345000000.0},
    }
    hass.data["homekit_controller-devices"][HKID] = new_connection
    await _poll(hass, freezer)

    assert float(hass.states.get(POWER).state) == pytest.approx(2.0)


async def test_switch_removed(
    hass: HomeAssistant, connection: FakeConnection, config_entry: MockConfigEntry
) -> None:
    """Deleting the switch from HomeKit Device deletes its entry and sensors."""
    other = add_paired_device(hass, HKID_2, "Outdoor Switch 2")
    other_entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        title="Outdoor Switch 2",
        unique_id=HKID_2.lower(),
        data={CONF_HKID: HKID_2},
    )
    other_entry.add_to_hass(hass)
    # Loading the integration sets up both entries.
    assert await _setup(hass, config_entry)
    assert other_entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_remove(connection.config_entry.entry_id)
    await hass.async_block_till_done()

    assert hass.config_entries.async_get_entry(config_entry.entry_id) is None
    assert er.async_get(hass).async_get(POWER) is None
    assert not dr.async_get(hass).async_get_devices(
        identifiers={device_identifier(HKID, 1)}
    )
    assert hass.states.get(POWER) is None
    # The other switch is untouched.
    assert other_entry.state is ConfigEntryState.LOADED
    assert other.get_characteristics.await_count == 1


async def test_other_switches_offered(
    hass: HomeAssistant, connection: FakeConnection, config_entry: MockConfigEntry
) -> None:
    """Once the integration is loaded, other paired switches are discovered."""
    add_paired_device(hass, HKID_2, "Outdoor Switch 2")
    assert await _setup(hass, config_entry)

    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert len(flows) == 1
    assert flows[0]["context"]["source"] == SOURCE_INTEGRATION_DISCOVERY
    assert flows[0]["context"]["unique_id"] == HKID_2.lower()
    assert flows[0]["step_id"] == "confirm"


async def test_migrate_single_entry(
    hass: HomeAssistant, connection: FakeConnection
) -> None:
    """The 0.1.0 entry for all switches is replaced by discovered switches."""
    old_entry = MockConfigEntry(
        domain=DOMAIN, version=1, title="iDevices HomeKit Power", data={}
    )
    old_entry.add_to_hass(hass)
    await _setup(hass, old_entry)

    assert hass.config_entries.async_get_entry(old_entry.entry_id) is None
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["unique_id"] for flow in flows] == [HKID.lower()]


async def _next_switch_read(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory
) -> None:
    freezer.tick(timedelta(seconds=SWITCH_READ_INTERVAL))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)


async def test_switch_change_reads_power(
    hass: HomeAssistant,
    connection: FakeConnection,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Power is read a few times, 2 seconds apart, after the switch changes."""
    assert await _setup(hass, config_entry)
    assert connection.get_characteristics.await_count == 1

    connection.push(ON_IID)
    connection.push(ON_IID)  # a quick off and on is read as one change
    await hass.async_block_till_done()
    assert connection.get_characteristics.await_count == 1

    for read in range(1, SWITCH_READ_COUNT + 1):
        connection.get_characteristics.return_value = {
            POWER_IID: {"value": read * 1000},
            ENERGY_IID: {"value": 12345000000.0},
        }
        await _next_switch_read(hass, freezer)
        assert connection.get_characteristics.await_count == 1 + read
        assert float(hass.states.get(POWER).state) == read

    await _next_switch_read(hass, freezer)
    assert connection.get_characteristics.await_count == 1 + SWITCH_READ_COUNT


async def test_switch_change_restarts_reads(
    hass: HomeAssistant,
    connection: FakeConnection,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A change while power is being read starts the reads over."""
    assert await _setup(hass, config_entry)

    connection.push(ON_IID)
    await _next_switch_read(hass, freezer)
    await _next_switch_read(hass, freezer)
    assert connection.get_characteristics.await_count == 3

    connection.push(ON_IID)
    for _ in range(SWITCH_READ_COUNT + 1):
        await _next_switch_read(hass, freezer)
    assert connection.get_characteristics.await_count == 3 + SWITCH_READ_COUNT


async def test_switch_watch_follows_reload(
    hass: HomeAssistant,
    connection: FakeConnection,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """After homekit_controller reloads, its new connection is followed."""
    assert await _setup(hass, config_entry)

    new_connection = FakeConnection(connection.config_entry, HKID, ACCESSORIES)
    hass.data["homekit_controller-devices"][HKID] = new_connection
    await _poll(hass, freezer)
    assert connection.subscriptions == {}
    assert set(new_connection.subscriptions) == {ON_IID}

    new_connection.push(ON_IID)
    await _next_switch_read(hass, freezer)
    assert new_connection.get_characteristics.await_count == 2


async def test_unload_stops_watching(
    hass: HomeAssistant,
    connection: FakeConnection,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Unloading drops the subscription and the remaining reads."""
    assert await _setup(hass, config_entry)
    assert set(connection.subscriptions) == {ON_IID}

    connection.push(ON_IID)
    await _next_switch_read(hass, freezer)
    assert connection.get_characteristics.await_count == 2

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    for _ in range(SWITCH_READ_COUNT):
        await _next_switch_read(hass, freezer)

    assert connection.subscriptions == {}
    assert connection.get_characteristics.await_count == 2


async def test_failed_setup_stops_watching(
    hass: HomeAssistant, connection: FakeConnection, config_entry: MockConfigEntry
) -> None:
    """A setup that fails its first read leaves no subscription behind."""
    connection.get_characteristics.side_effect = AccessoryDisconnectedError("gone")
    assert not await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.SETUP_RETRY
    assert connection.subscriptions == {}
