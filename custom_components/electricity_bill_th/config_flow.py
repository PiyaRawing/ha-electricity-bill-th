"""Config flow for Thai Electricity Bill integration."""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
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

    def __init__(self):
        """Initialize the config flow."""
        self.provider = None

    async def async_step_user(self, user_input=None):
        """Step 1: เลือกการไฟฟ้า."""
        if user_input is not None:
            self.provider = user_input[CONF_PROVIDER]
            return await self.async_step_details()

        data_schema = vol.Schema({
            vol.Required(CONF_PROVIDER, default="MEA"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=["MEA", "PEA"],
                    mode=selector.SelectSelectorMode.DROPDOWN
                )
            )
        })

        return self.async_show_form(
            step_id="user", data_schema=data_schema
        )

    async def async_step_details(self, user_input=None):
        """Step 2: เลือกประเภทและตั้งค่าที่เหลือ."""
        errors = {}

        if user_input is not None:
            if not (1 <= int(user_input[CONF_BILLING_DATE]) <= 31):
                errors["base"] = "invalid_date"
            else:
                user_input[CONF_PROVIDER] = self.provider 
                title = f"{self.provider} ({user_input[CONF_TARIFF_TYPE]})"
                return self.async_create_entry(title=title, data=user_input)

        if self.provider == "PEA":
            options = [
                selector.SelectOptionDict(value="1.1.1", label="1.1.1 (บ้านที่ใช้ไฟไม่เกิน 150 หน่วย)"),
                selector.SelectOptionDict(value="1.1.2", label="1.1.2 (บ้านที่ใช้ไฟเกิน 150 หน่วย)"),
                selector.SelectOptionDict(value="1.2.2", label="1.2.2 (TOU แรงดัน < 22kV)"),
            ]
            default_tariff = "1.1.2"
        else:
            options = [
                selector.SelectOptionDict(value="1.1", label="1.1 (บ้านที่ใช้ไฟไม่เกิน 150 หน่วย)"),
                selector.SelectOptionDict(value="1.2", label="1.2 (บ้านที่ใช้ไฟเกิน 150 หน่วย)"),
                selector.SelectOptionDict(value="1.3.2", label="1.3.2 (TOU แรงดัน < 22kV)"),
            ]
            default_tariff = "1.2"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_TARIFF_TYPE, default=default_tariff): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.DROPDOWN
                    )
                ),
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
            step_id="details", data_schema=data_schema, errors=errors
        )