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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """บอก HA ว่ามีระบบ Re-Config (Options)."""
        return ElectricityBillOptionsFlow(config_entry)

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
            step_id="user", 
            data_schema=data_schema,
            last_step=False
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
                    selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
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
            step_id="details", 
            data_schema=data_schema, 
            errors=errors,
            last_step=True
        )

class ElectricityBillOptionsFlow(config_entries.OptionsFlow):
    """Handle options (Re-config) for the integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        errors = {}
        if user_input is not None:
            if not (1 <= int(user_input.get(CONF_BILLING_DATE, 14)) <= 31):
                errors["base"] = "invalid_date"
            else:
                return self.async_create_entry(title="", data=user_input)

        config = self.config_entry.options if self.config_entry.options else self.config_entry.data
        provider = self.config_entry.data.get(CONF_PROVIDER, "MEA")

        # เปลี่ยนมาใช้ Dictionary ธรรมดา เพื่อป้องกันบัคใน Home Assistant บางเวอร์ชั่น
        if provider == "PEA":
            options = [
                {"value": "1.1.1", "label": "1.1.1 (บ้านที่ใช้ไฟไม่เกิน 150 หน่วย)"},
                {"value": "1.1.2", "label": "1.1.2 (บ้านที่ใช้ไฟเกิน 150 หน่วย)"},
                {"value": "1.2.2", "label": "1.2.2 (TOU แรงดัน < 22kV)"},
            ]
        else:
            options = [
                {"value": "1.1", "label": "1.1 (บ้านที่ใช้ไฟไม่เกิน 150 หน่วย)"},
                {"value": "1.2", "label": "1.2 (บ้านที่ใช้ไฟเกิน 150 หน่วย)"},
                {"value": "1.3.2", "label": "1.3.2 (TOU แรงดัน < 22kV)"},
            ]

        schema_dict = {}

        # 1. Tariff Type (เขียนเช็คกันค่าว่างเพื่อป้องกัน Error 500)
        tariff = config.get(CONF_TARIFF_TYPE)
        if tariff:
            schema_dict[vol.Required(CONF_TARIFF_TYPE, default=tariff)] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
            )
        else:
            schema_dict[vol.Required(CONF_TARIFF_TYPE)] = selector.SelectSelector(
                selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN)
            )

        # 2. Billing Date
        b_date = config.get(CONF_BILLING_DATE, 14)
        schema_dict[vol.Required(CONF_BILLING_DATE, default=int(b_date))] = vol.All(vol.Coerce(int), vol.Range(min=1, max=31))

        # 3. FT Rate
        ft = config.get(CONF_FT_RATE, 0.1623)
        schema_dict[vol.Required(CONF_FT_RATE, default=float(ft))] = vol.Coerce(float)

        # 4. Imported Energy
        imp = config.get(CONF_ENERGY_IMPORTED)
        if imp:
            schema_dict[vol.Required(CONF_ENERGY_IMPORTED, default=imp)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            )
        else:
            schema_dict[vol.Required(CONF_ENERGY_IMPORTED)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            )

        # 5. Exported Energy
        exp = config.get(CONF_ENERGY_EXPORTED)
        if exp:
            schema_dict[vol.Optional(CONF_ENERGY_EXPORTED, default=exp)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            )
        else:
            schema_dict[vol.Optional(CONF_ENERGY_EXPORTED)] = selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            )

        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(schema_dict), errors=errors
        )