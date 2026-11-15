"""Polling coordinator for the iDevices HomeKit Power integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from aiohomekit.exceptions import HomeKitException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_HKID, DEFAULT_SCAN_INTERVAL, DOMAIN
from .hkc import async_get_connection

_LOGGER = logging.getLogger(__name__)

type IDevicesPowerConfigEntry = ConfigEntry[IDevicesPowerCoordinator]


class IDevicesPowerCoordinator(DataUpdateCoordinator[dict[tuple[int, int], Any]]):
    """Reads one switch's power characteristics, which it never pushes."""

    config_entry: IDevicesPowerConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: IDevicesPowerConfigEntry,
        characteristics: set[tuple[int, int]],
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=scan_interval(entry),
        )
        self.hkid: str = entry.data[CONF_HKID]
        self.characteristics = characteristics

    async def _async_update_data(self) -> dict[tuple[int, int], Any]:
        """Fetch the latest readings over homekit_controller's pairing."""
        # Look the connection up every time: it is replaced if
        # homekit_controller reloads its config entry.
        if (conn := async_get_connection(self.hass, self.hkid)) is None:
            raise UpdateFailed(f"HomeKit device {self.hkid} is not loaded")
        try:
            results = await conn.get_characteristics(self.characteristics)
        except (HomeKitException, TimeoutError) as err:
            raise UpdateFailed(f"Error reading {self.hkid}: {err}") from err
        return {
            aid_iid: result["value"]
            for aid_iid, result in results.items()
            if "value" in result
        }


def scan_interval(entry: ConfigEntry) -> timedelta:
    """Return the polling interval configured for an entry."""
    return timedelta(
        seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
