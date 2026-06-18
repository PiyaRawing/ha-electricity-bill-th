"""Config flow for Thai Electricity Bill integration."""
from __future__ import annotations

import logging
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

_LOGGER = logging.getLogger(__name__)

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

        # ใช้ vol.In เพื่อความเข้ากันได้ 100% กับ HA ทุกเวอร์ชั่น
        data_schema = vol.Schema({
            vol.Required(CONF_PROVIDER, default="MEA"): vol.In({"MEA": "MEA", "PEA": "PEA"})
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
            try:
                b_date = int(user_input[CONF_BILLING_DATE])
                if not (1 <= b_date <= 31):
                    errors["base"] = "invalid_date"
            except ValueError:
                errors["base"] = "invalid_date"
                
            if not errors:
                user_input[CONF_PROVIDER] = self.provider 
                title = f"{self.provider} ({user_input[CONF_TARIFF_TYPE]})"
                return self.async_create_entry(title=title, data=user_input)

        # ใช้ vol.In เป็น Dictionary พื้นฐาน ไม่แครชแน่นอน
        if self.provider == "PEA":
            tariffs = {
                "1.1.1": "1.1.1 (บ้านที่ใช้ไฟไม่เกิน 150 หน่วย)",
                "1.1.2": "1.1.2 (บ้านที่ใช้ไฟเกิน 150 หน่วย)",
                "1.2.2": "1.2.2 (TOU แรงดัน < 22kV)"
            }
            default_tariff = "1.1.2"
        else:
            tariffs = {
                "1.1": "1.1 (บ้านที่ใช้ไฟไม่เกิน 150 หน่วย)",
                "1.2": "1.2 (บ้านที่ใช้ไฟเกิน 150 หน่วย)",
                "1.3.2": "1.3.2 (TOU แรงดัน < 22kV)"
            }
            default_tariff = "1.2"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_TARIFF_TYPE, default=default_tariff): vol.In(tariffs),
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
        try:
            if user_input is not None:
                try:
                    b_date = int(user_input[CONF_BILLING_DATE])
                    if not (1 <= b_date <= 31):
                        errors["base"] = "invalid_date"
                except ValueError:
                    errors["base"] = "invalid_date"
                    
                if not errors:
                    return self.async_create_entry(title="", data=user_input)

            config = self.config_entry.options if self.config_entry.options else self.config_entry.data
            provider = self.config_entry.data.get(CONF_PROVIDER, "MEA")

            if provider == "PEA":
                tariffs = {
                    "1.1.1": "1.1.1 (บ้านที่ใช้ไฟไม่เกิน 150 หน่วย)",
                    "1.1.2": "1.1.2 (บ้านที่ใช้ไฟเกิน 150 หน่วย)",
                    "1.2.2": "1.2.2 (TOU แรงดัน < 22kV)"
                }
            else:
                tariffs = {
                    "1.1": "1.1 (บ้านที่ใช้ไฟไม่เกิน 150 หน่วย)",
                    "1.2": "1.2 (บ้านที่ใช้ไฟเกิน 150 หน่วย)",
                    "1.3.2": "1.3.2 (TOU แรงดัน < 22kV)"
                }

            # ดักบัค Error 500: ถ้าค่าเริ่มต้นไม่อยู่ในลิสต์ ให้เอาตัวแรกในลิสต์มาใช้เลย
            tariff = config.get(CONF_TARIFF_TYPE)
            if tariff not in tariffs:
                tariff = list(tariffs.keys())[0]
            
            try: b_date = int(config.get(CONF_BILLING_DATE, 14))
            except (ValueError, TypeError): b_date = 14
            
            try: ft = float(config.get(CONF_FT_RATE, 0.1623))
            except (ValueError, TypeError): ft = 0.1623
            
            imp = config.get(CONF_ENERGY_IMPORTED)
            exp = config.get(CONF_ENERGY_EXPORTED)

            schema_dict = {
                vol.Required(CONF_TARIFF_TYPE, default=tariff): vol.In(tariffs),
                vol.Required(CONF_BILLING_DATE, default=b_date): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
                vol.Required(CONF_FT_RATE, default=ft): vol.Coerce(float),
            }

            if imp:
                schema_dict[vol.Required(CONF_ENERGY_IMPORTED, default=imp)] = selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                )
            else:
                schema_dict[vol.Required(CONF_ENERGY_IMPORTED)] = selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor")
                )

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
        except Exception as e:
            _LOGGER.error("Error generating options flow: %s", e)
            raise