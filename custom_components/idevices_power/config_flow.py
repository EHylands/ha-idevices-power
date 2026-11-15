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

from .const import DEFAULT_SCAN_INTERVAL, DOMAIN
from .hkc import async_loaded_connections, metered_characteristics

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
    """Set up power sensors for every paired iDevices switch."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> IDevicesPowerOptionsFlow:
        """Return the options flow."""
        return IDevicesPowerOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm, showing the switches found so far."""
        if user_input is not None:
            return self.async_create_entry(title="iDevices HomeKit Power", data={})

        names = sorted(
            conn.config_entry.title
            for conn in async_loaded_connections(self.hass)
            if metered_characteristics(conn)
        )
        if not names:
            return self.async_abort(reason="no_devices")

        return self.async_show_form(
            step_id="user",
            description_placeholders={"devices": "\n".join(f"- {n}" for n in names)},
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
