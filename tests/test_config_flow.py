"""Tests for the iDevices HomeKit Power config flow."""

from __future__ import annotations

from datetime import timedelta
from ipaddress import ip_address

import pytest

from homeassistant.config_entries import SOURCE_USER, SOURCE_ZEROCONF, ConfigEntryState
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.idevices_power.const import CONF_HKID, DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import (
    HKID,
    OTHER_ACCESSORIES,
    TITLE,
    FakeConnection,
    add_paired_device,
)


def _zeroconf(hkid: str, model: str = "IDEV0004") -> ZeroconfServiceInfo:
    """Return an advertisement like the switch's, with HAP's upper-case keys."""
    return ZeroconfServiceInfo(
        ip_address=ip_address("192.0.2.10"),
        ip_addresses=[ip_address("192.0.2.10")],
        hostname="switch.local.",
        name=f"{TITLE}._hap._tcp.local.",
        port=80,
        type="_hap._tcp.local.",
        properties={"ID": hkid.lower(), "MD": model, "sf": "0", "c#": "2"},
    )


async def test_user_flow(hass: HomeAssistant, connection: FakeConnection) -> None:
    """A paired switch can be picked and is not offered twice."""
    add_paired_device(hass, "11:22:33:44:55:66", "Light", OTHER_ACCESSORIES)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert list(result["data_schema"].schema[CONF_HKID].container) == [HKID]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HKID: HKID}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == TITLE
    assert result["data"] == {CONF_HKID: HKID}
    assert result["result"].unique_id == HKID.lower()
    assert result["result"].state is ConfigEntryState.LOADED

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices"


async def test_user_flow_no_devices(hass: HomeAssistant) -> None:
    """The flow aborts when no loaded pairing has power metering."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices"


async def test_zeroconf_discovery(
    hass: HomeAssistant, connection: FakeConnection
) -> None:
    """An advertised, paired switch is offered for confirmation."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=_zeroconf(HKID)
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    assert result["description_placeholders"] == {"name": TITLE}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == TITLE
    # Stored as homekit_controller spells it, not as advertised.
    assert result["data"] == {CONF_HKID: HKID}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=_zeroconf(HKID)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    ("state", "accessories", "reason"),
    [
        (None, None, "not_paired"),
        (ConfigEntryState.SETUP_RETRY, None, "not_loaded"),
        (ConfigEntryState.LOADED, OTHER_ACCESSORIES, "not_supported"),
    ],
)
async def test_zeroconf_not_offered(
    hass: HomeAssistant,
    state: ConfigEntryState | None,
    accessories: list | None,
    reason: str,
) -> None:
    """Devices that can't be read are not offered."""
    if state is not None:
        kwargs = {"accessories": accessories} if accessories else {}
        add_paired_device(hass, HKID, TITLE, state=state, **kwargs)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_ZEROCONF}, data=_zeroconf(HKID)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason


async def test_options_flow(
    hass: HomeAssistant, connection: FakeConnection, config_entry: MockConfigEntry
) -> None:
    """Changing the polling interval applies without a reload."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 10}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.runtime_data.update_interval == timedelta(seconds=10)
