"""Tests for the iDevices HomeKit Power config flow."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.idevices_power.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import TITLE, FakeConnection


async def test_user_flow(hass: HomeAssistant, connection: FakeConnection) -> None:
    """The found switches are listed, and only one entry can be made."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["description_placeholders"] == {"devices": f"- {TITLE}"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "iDevices HomeKit Power"
    assert result["data"] == {}

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_user_flow_no_devices(hass: HomeAssistant) -> None:
    """The flow aborts when no loaded pairing has power metering."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices"


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
