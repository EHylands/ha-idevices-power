"""Power and energy sensors for iDevices switches paired with homekit_controller."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import (
    IDevicesPowerConfigEntry,
    IDevicesPowerCoordinator,
    scan_interval,
)

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: IDevicesPowerConfigEntry
) -> bool:
    """Set up power sensors for all paired iDevices switches."""
    coordinator = IDevicesPowerCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: IDevicesPowerConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_options_updated(
    hass: HomeAssistant, entry: IDevicesPowerConfigEntry
) -> None:
    """Apply a new polling interval."""
    entry.runtime_data.update_interval = scan_interval(entry)
