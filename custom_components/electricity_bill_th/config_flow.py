"""Config flow for Thai Electricity Bill integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_PROVIDER,
    CONF_TARIFF_TYPE,
    CONF_BILLING_DATE,
    CONF_FT_RATE,
    CONF_ENERGY_IMPORTED,
    CONF_ENERGY_EXPORTED,
)

class ElectricityBillConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Thai Electricity Bill."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            if not (1 <= int(user_input[CONF_BILLING_DATE]) <= 31):
                errors["base"] = "invalid_date"
            else:
                title = f"{user_input[CONF_PROVIDER]} ({user_input[CONF_TARIFF_TYPE]})"
                return self.async_create_entry(title=title, data=user_input)
        # ใช้ selector.EntitySelector ของใหม่แทนเพื่อให้ UI ของ Home Assistant ทำงานได้ปกติ
        data_schema = vol.Schema(
            {
                vol.Required(CONF_PROVIDER, default="MEA"): vol.In(["MEA", "PEA"]),
                vol.Required(CONF_TARIFF_TYPE, default="1.2"): vol.In(["1.2"]),
                vol.Required(CONF_BILLING_DATE, default=14): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
                vol.Required(CONF_FT_RATE, default=0.1623): vol.Coerce(float),
                vol.Required(CONF_ENERGY_IMPORTED): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
                vol.Optional(CONF_ENERGY_EXPORTED): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                ),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )