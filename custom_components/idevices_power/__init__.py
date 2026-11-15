"""Power and energy sensors for iDevices switches paired with homekit_controller."""

from __future__ import annotations

import logging

from homeassistant.config_entries import (
    SIGNAL_CONFIG_ENTRY_CHANGED,
    SOURCE_INTEGRATION_DISCOVERY,
    ConfigEntry,
    ConfigEntryChange,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, discovery_flow
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.typing import ConfigType

from .const import CONF_HKID, DOMAIN
from .coordinator import (
    IDevicesPowerConfigEntry,
    IDevicesPowerCoordinator,
    scan_interval,
)
from .hkc import (
    HKC_DOMAIN,
    async_get_connection,
    async_get_pairing_entry,
    async_loaded_connections,
    metered_characteristics,
    switch_characteristics,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Offer every paired switch with power metering as a discovered device.

    Zeroconf discovery only matches iDevices model names; this also finds
    devices it missed, once at least one switch has been added.
    """
    for conn in async_loaded_connections(hass):
        if metered_characteristics(conn):
            discovery_flow.async_create_flow(
                hass,
                DOMAIN,
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data={CONF_HKID: conn.unique_id},
            )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: IDevicesPowerConfigEntry
) -> bool:
    """Set up power sensors on top of an existing HomeKit pairing."""
    hkid = entry.data[CONF_HKID]
    if async_get_pairing_entry(hass, hkid) is None:
        raise ConfigEntryError(
            f"{entry.title} is no longer paired with the HomeKit Device integration"
        )
    if (conn := async_get_connection(hass, hkid)) is None:
        raise ConfigEntryNotReady(f"HomeKit device {entry.title} is not loaded yet")

    characteristics = {(aid, iid) for aid, _, iid in metered_characteristics(conn)}
    coordinator = IDevicesPowerCoordinator(
        hass, entry, characteristics, switch_characteristics(conn)
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    @callback
    def _async_pairing_changed(change: ConfigEntryChange, changed: ConfigEntry) -> None:
        """Remove this entry when the switch is deleted from HomeKit Device."""
        if (
            change is ConfigEntryChange.REMOVED
            and changed.domain == HKC_DOMAIN
            and changed.unique_id == hkid.lower()
        ):
            hass.async_create_task(hass.config_entries.async_remove(entry.entry_id))

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_CONFIG_ENTRY_CHANGED, _async_pairing_changed
        )
    )
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: IDevicesPowerConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Replace the single entry 0.1.0 used for all switches."""
    if entry.version == 1:
        # async_setup has already offered each switch as a discovered device.
        _LOGGER.warning(
            "iDevices HomeKit Power now has one entry per switch; add your "
            "switches from the discovered devices in Devices & services"
        )
        hass.async_create_task(hass.config_entries.async_remove(entry.entry_id))
        return False
    return True


async def _async_options_updated(
    hass: HomeAssistant, entry: IDevicesPowerConfigEntry
) -> None:
    """Apply a new polling interval."""
    entry.runtime_data.update_interval = scan_interval(entry)
