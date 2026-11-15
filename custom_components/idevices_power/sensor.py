"""Power and energy sensors for iDevices switches."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CHAR_ENERGY, CHAR_POWER
from .coordinator import IDevicesPowerConfigEntry, IDevicesPowerCoordinator
from .hkc import async_get_connection, device_info, metered_characteristics

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
    """Set up the sensors."""
    coordinator = entry.runtime_data
    conn = async_get_connection(hass, coordinator.hkid)
    assert conn is not None  # checked in async_setup_entry
    async_add_entities(
        IDevicesPowerSensor(
            coordinator, SENSORS[char_type], aid, iid, device_info(conn, aid)
        )
        for aid, char_type, iid in metered_characteristics(conn)
    )


class IDevicesPowerSensor(CoordinatorEntity[IDevicesPowerCoordinator], SensorEntity):
    """A power or energy reading from an iDevices switch."""

    _attr_has_entity_name = True
    entity_description: IDevicesSensorEntityDescription

    def __init__(
        self,
        coordinator: IDevicesPowerCoordinator,
        description: IDevicesSensorEntityDescription,
        aid: int,
        iid: int,
        device: DeviceInfo,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._aid_iid = (aid, iid)
        self._attr_unique_id = f"{coordinator.hkid}_{aid}_{iid}"
        self._attr_device_info = device

    @property
    def available(self) -> bool:
        """Return True if the last poll returned a value for this sensor."""
        return super().available and self._aid_iid in self.coordinator.data

    @property
    def native_value(self) -> float:
        """Return the reading in Home Assistant units."""
        return self.coordinator.data[self._aid_iid] / self.entity_description.divisor
