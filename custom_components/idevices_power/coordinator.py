"""Polling coordinator for the iDevices HomeKit Power integration."""

from __future__ import annotations

from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from aiohomekit.exceptions import HomeKitException

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_HKID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SWITCH_READ_COUNT,
    SWITCH_READ_INTERVAL,
)
from .hkc import async_get_connection

if TYPE_CHECKING:
    from homeassistant.components.homekit_controller.connection import HKDevice

_LOGGER = logging.getLogger(__name__)

type IDevicesPowerConfigEntry = ConfigEntry[IDevicesPowerCoordinator]


class IDevicesPowerCoordinator(DataUpdateCoordinator[dict[tuple[int, int], Any]]):
    """Reads one switch's power characteristics, which it never pushes.

    Besides polling, power is read a few times in quick succession after the
    switch turns on or off, which it does push.
    """

    config_entry: IDevicesPowerConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: IDevicesPowerConfigEntry,
        characteristics: set[tuple[int, int]],
        switch_characteristics: set[tuple[int, int]],
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
        self._switch_characteristics = switch_characteristics
        self._watched_conn: HKDevice | None = None
        self._unwatch: CALLBACK_TYPE | None = None
        self._cancel_switch_read: CALLBACK_TYPE | None = None
        self._switch_reads_left = 0

    @callback
    def async_watch_switch(self, conn: HKDevice) -> None:
        """Follow on/off changes pushed to this connection.

        Called again on every poll, as homekit_controller replaces the
        connection when it reloads.
        """
        if conn is self._watched_conn:
            return
        self._async_unwatch_switch()
        self._watched_conn = conn
        if self._switch_characteristics:
            self._unwatch = conn.async_subscribe(
                self._switch_characteristics, self._async_switch_changed
            )

    @callback
    def _async_unwatch_switch(self) -> None:
        if self._unwatch is not None:
            self._unwatch()
            self._unwatch = None
        self._watched_conn = None

    @callback
    def _async_switch_changed(self) -> None:
        """Read power a few times as it settles after the switch changed.

        A change during the reads starts them over.
        """
        self._switch_reads_left = SWITCH_READ_COUNT
        self._async_schedule_switch_read()

    @callback
    def _async_schedule_switch_read(self) -> None:
        if self._cancel_switch_read is not None:
            self._cancel_switch_read()
        self._cancel_switch_read = async_call_later(
            self.hass, SWITCH_READ_INTERVAL, self._async_read_after_switch
        )

    async def _async_read_after_switch(self, _now: datetime) -> None:
        self._cancel_switch_read = None
        self._switch_reads_left -= 1
        # Not async_request_refresh: its cooldown would hold back reads this
        # close together.
        await self.async_refresh()
        # Unless a change or shutdown came in during the read.
        if self._switch_reads_left > 0 and self._cancel_switch_read is None:
            self._async_schedule_switch_read()

    async def async_shutdown(self) -> None:
        """Stop following the switch."""
        self._switch_reads_left = 0
        if self._cancel_switch_read is not None:
            self._cancel_switch_read()
            self._cancel_switch_read = None
        self._async_unwatch_switch()
        await super().async_shutdown()

    async def _async_update_data(self) -> dict[tuple[int, int], Any]:
        """Fetch the latest readings over homekit_controller's pairing."""
        # Look the connection up every time: it is replaced if
        # homekit_controller reloads its config entry.
        if (conn := async_get_connection(self.hass, self.hkid)) is None:
            raise UpdateFailed(f"HomeKit device {self.hkid} is not loaded")
        self.async_watch_switch(conn)
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
