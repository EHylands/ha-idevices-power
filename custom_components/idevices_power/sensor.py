"""Power and energy sensors for iDevices switches."""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CHAR_ENERGY, CHAR_POWER
from .coordinator import IDevicesPowerConfigEntry, IDevicesPowerCoordinator, ReadingKey
from .hkc import async_get_connection, async_get_device

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class IDevicesSensorEntityDescription(SensorEntityDescription):
    """Describes an iDevices sensor."""

    # The device reports units Home Assistant has no unit for.
    divisor: float


SENSORS: dict[str, IDevicesSensorEntityDescription] = {
    CHAR_POWER: IDevicesSensorEntityDescription(
        key="power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=1,
        divisor=1000,  # mW -> W
    ),
    CHAR_ENERGY: IDevicesSensorEntityDescription(
        key="energy",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=3,
        divisor=3_600_000_000,  # mJ -> kWh
    ),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IDevicesPowerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors, adding more whenever a poll finds a new switch."""
    coordinator = entry.runtime_data
    known: set[ReadingKey] = set()

    @callback
    def _async_add_new_sensors() -> None:
        new_sensors = []
        for key in coordinator.metered.keys() - known:
            hkid, aid, _ = key
            conn = async_get_connection(hass, hkid)
            sensor = IDevicesPowerSensor(
                coordinator,
                SENSORS[coordinator.metered[key]],
                key,
                async_get_device(hass, conn, aid) if conn else None,
            )
            # Let a removed sensor be found again if its switch comes back.
            sensor.async_on_remove(partial(known.discard, key))
            known.add(key)
            new_sensors.append(sensor)
        if new_sensors:
            async_add_entities(new_sensors)

    _async_add_new_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_async_add_new_sensors))


class IDevicesPowerSensor(CoordinatorEntity[IDevicesPowerCoordinator], SensorEntity):
    """A power or energy reading from an iDevices switch."""

    _attr_has_entity_name = True
    entity_description: IDevicesSensorEntityDescription

    def __init__(
        self,
        coordinator: IDevicesPowerCoordinator,
        description: IDevicesSensorEntityDescription,
        key: ReadingKey,
        device: dr.DeviceEntry | None,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._key = key
        hkid, aid, iid = key
        self._attr_unique_id = f"{hkid}_{aid}_{iid}"
        # Show up on the device homekit_controller created, rather than a new one.
        self.device_entry = device
        self._linked_device_id = device.id if device else None

    @callback
    def async_registry_entry_updated(self) -> None:
        """Remove this sensor once homekit_controller deletes its device.

        Home Assistant only unlinks another integration's entities from a
        deleted device, leaving them behind.
        """
        assert self.registry_entry is not None
        if self._linked_device_id is not None and self.registry_entry.device_id is None:
            # Not while Home Assistant is still applying the update.
            self.hass.loop.call_soon(self._async_remove_from_registry)

    @callback
    def _async_remove_from_registry(self) -> None:
        """Delete this sensor's entity registry entry."""
        entity_registry = er.async_get(self.hass)
        if entity_registry.async_get(self.entity_id) is not None:
            entity_registry.async_remove(self.entity_id)

    @property
    def available(self) -> bool:
        """Return True if the last poll returned a value for this sensor."""
        return super().available and self._key in self.coordinator.data

    @property
    def native_value(self) -> float:
        """Return the reading in Home Assistant units."""
        return self.coordinator.data[self._key] / self.entity_description.divisor
