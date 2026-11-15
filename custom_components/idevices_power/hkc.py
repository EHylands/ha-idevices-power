"""Access to the pairings managed by the homekit_controller integration.

homekit_controller has no public API for sharing its connections, so all
knowledge of its internals is kept in this module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CHAR_ENERGY, CHAR_POWER, SERVICE_POWER

if TYPE_CHECKING:
    from homeassistant.components.homekit_controller.connection import HKDevice

HKC_DOMAIN = "homekit_controller"

# Mirrors homekit_controller.const; not imported so that loading this module
# does not pull in all of homekit_controller's dependencies.
KNOWN_DEVICES = f"{HKC_DOMAIN}-devices"
IDENTIFIER_ACCESSORY_ID = f"{HKC_DOMAIN}:accessory-id"


@callback
def async_loaded_connections(hass: HomeAssistant) -> list[HKDevice]:
    """Return every homekit_controller connection that is set up."""
    connections: dict[str, HKDevice] = hass.data.get(KNOWN_DEVICES, {})
    return [
        conn
        for conn in connections.values()
        if conn.config_entry.state is ConfigEntryState.LOADED
    ]


@callback
def async_get_connection(hass: HomeAssistant, hkid: str) -> HKDevice | None:
    """Return the connection for a pairing id, if it is set up.

    The pairing id is matched in any letter case, as zeroconf and
    homekit_controller do not agree on one.
    """
    for conn in async_loaded_connections(hass):
        if conn.unique_id.lower() == hkid.lower():
            return conn
    return None


@callback
def async_get_pairing_entry(hass: HomeAssistant, hkid: str) -> ConfigEntry | None:
    """Return homekit_controller's config entry for a pairing id, loaded or not."""
    return hass.config_entries.async_entry_for_domain_unique_id(
        HKC_DOMAIN, hkid.lower()
    )


def metered_characteristics(conn: HKDevice) -> list[tuple[int, str, int]]:
    """Return (aid, characteristic type, iid) for each power/energy reading."""
    found = []
    for accessory in conn.entity_map.accessories:
        if (service := accessory.services.first(service_type=SERVICE_POWER)) is None:
            continue
        for char_type in (CHAR_POWER, CHAR_ENERGY):
            if service.has(char_type):
                found.append((accessory.aid, char_type, service[char_type].iid))
    return found


def device_identifier(hkid: str, aid: int) -> tuple[str, str]:
    """Return the device registry identifier homekit_controller uses."""
    return (IDENTIFIER_ACCESSORY_ID, f"{hkid}:aid:{aid}")


def device_info(conn: HKDevice, aid: int) -> DeviceInfo:
    """Describe an accessory as homekit_controller does.

    Sharing homekit_controller's identifier makes Home Assistant show this
    integration's device as linked to homekit_controller's: the same physical
    switch, provided by both integrations.
    """
    accessory = conn.entity_map.aid(aid)
    return DeviceInfo(
        identifiers={device_identifier(conn.unique_id, aid)},
        name=accessory.name,
        manufacturer=accessory.manufacturer,
        model=accessory.model,
        serial_number=accessory.serial_number,
        sw_version=accessory.firmware_revision,
        hw_version=accessory.hardware_revision,
    )
