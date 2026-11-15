"""Polling coordinator for the iDevices HomeKit Power integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from aiohomekit.exceptions import HomeKitException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .hkc import async_loaded_connections, metered_characteristics

if TYPE_CHECKING:
    from homeassistant.components.homekit_controller.connection import HKDevice

_LOGGER = logging.getLogger(__name__)

type IDevicesPowerConfigEntry = ConfigEntry[IDevicesPowerCoordinator]

# (pairing id, aid, iid) of one power or energy characteristic.
type ReadingKey = tuple[str, int, int]


class IDevicesPowerCoordinator(DataUpdateCoordinator[dict[ReadingKey, Any]]):
    """Finds and reads every power characteristic, which devices never push."""

    config_entry: IDevicesPowerConfigEntry

    def __init__(self, hass: HomeAssistant, entry: IDevicesPowerConfigEntry) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=scan_interval(entry),
        )
        # Characteristic type of every reading found on the last poll.
        self.metered: dict[ReadingKey, str] = {}
        self._unreachable: set[str] = set()

    async def _async_update_data(self) -> dict[ReadingKey, Any]:
        """Read all devices that have the power service.

        Connections are looked up on every poll, so switches paired or
        reconnected since the last poll are picked up.
        """
        metered: dict[ReadingKey, str] = {}
        reads = []
        for conn in async_loaded_connections(self.hass):
            if not (chars := metered_characteristics(conn)):
                continue
            for aid, char_type, iid in chars:
                metered[(conn.unique_id, aid, iid)] = char_type
            reads.append(self._async_read(conn, {(aid, iid) for aid, _, iid in chars}))
        self.metered = metered

        data: dict[ReadingKey, Any] = {}
        for readings in await asyncio.gather(*reads):
            data.update(readings)
        return data

    async def _async_read(
        self, conn: HKDevice, characteristics: set[tuple[int, int]]
    ) -> dict[ReadingKey, Any]:
        """Read one device; a failure only makes its own sensors unavailable."""
        hkid = conn.unique_id
        try:
            results = await conn.get_characteristics(characteristics)
        except (HomeKitException, TimeoutError) as err:
            if hkid not in self._unreachable:
                self._unreachable.add(hkid)
                _LOGGER.info(
                    "Can't read power from %s: %s", conn.config_entry.title, err
                )
            return {}
        if hkid in self._unreachable:
            self._unreachable.discard(hkid)
            _LOGGER.info("Reading power from %s again", conn.config_entry.title)
        return {
            (hkid, aid, iid): result["value"]
            for (aid, iid), result in results.items()
            if "value" in result
        }


def scan_interval(entry: ConfigEntry) -> timedelta:
    """Return the polling interval configured for an entry."""
    return timedelta(
        seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
