"""Config flow for the iDevices HomeKit Power integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_SCAN_INTERVAL, UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from homeassistant.helpers.typing import DiscoveryInfoType

from .const import CONF_HKID, DEFAULT_SCAN_INTERVAL, DOMAIN
from .hkc import (
    async_get_connection,
    async_get_pairing_entry,
    async_loaded_connections,
    metered_characteristics,
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): NumberSelector(
            NumberSelectorConfig(
                min=5,
                max=3600,
                step=1,
                unit_of_measurement=UnitOfTime.SECONDS,
                mode=NumberSelectorMode.BOX,
            )
        )
    }
)


class IDevicesPowerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add power sensors to one switch paired with homekit_controller."""

    # Version 1 was a single entry covering all switches.
    VERSION = 2

    _hkid: str
    _name: str

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> IDevicesPowerOptionsFlow:
        """Return the options flow."""
        return IDevicesPowerOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick one of the paired switches that report power."""
        configured = self._async_current_ids(include_ignore=False)
        devices = {
            conn.unique_id: conn.config_entry.title
            for conn in async_loaded_connections(self.hass)
            if conn.unique_id.lower() not in configured
            and metered_characteristics(conn)
        }

        if user_input is not None:
            hkid = user_input[CONF_HKID]
            await self.async_set_unique_id(hkid.lower())
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=devices[hkid], data={CONF_HKID: hkid})

        if not devices:
            return self.async_abort(reason="no_devices")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HKID): vol.In(devices)}),
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle an iDevices accessory advertised on the network."""
        properties = {
            key.lower(): value for key, value in discovery_info.properties.items()
        }
        if not (hkid := properties.get("id")):
            return self.async_abort(reason="invalid_discovery_info")
        return await self._async_handle_discovery(hkid)

    async def async_step_integration_discovery(
        self, discovery_info: DiscoveryInfoType
    ) -> ConfigFlowResult:
        """Handle a paired switch found by async_setup."""
        return await self._async_handle_discovery(discovery_info[CONF_HKID])

    async def _async_handle_discovery(self, hkid: str) -> ConfigFlowResult:
        """Offer a discovered switch if it is paired and reports power."""
        await self.async_set_unique_id(hkid.lower())
        self._abort_if_unique_id_configured()

        if async_get_pairing_entry(self.hass, hkid) is None:
            return self.async_abort(reason="not_paired")
        if (conn := async_get_connection(self.hass, hkid)) is None:
            return self.async_abort(reason="not_loaded")
        if not metered_characteristics(conn):
            return self.async_abort(reason="not_supported")

        self._hkid = conn.unique_id
        self._name = conn.config_entry.title
        self.context["title_placeholders"] = {"name": self._name}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding a discovered switch."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name, data={CONF_HKID: self._hkid}
            )

        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm", description_placeholders={"name": self._name}
        )


class IDevicesPowerOptionsFlow(OptionsFlow):
    """Change the polling interval."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
