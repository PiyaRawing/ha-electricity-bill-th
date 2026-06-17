"""The Thai Electricity Bill integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant 
from homeassistant.const import Platform

from .const import DOMAIN

# ระบุว่า Integration นี้จะสร้าง Entity ประเภทไหนบ้าง (ของเราคือ sensor)
PLATFORMS: list[Platform] = [Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Thai Electricity Bill from a config entry."""
    # สร้างพื้นที่เก็บข้อมูลสำหรับ Integration นี้ใน Home Assistant
    hass.data.setdefault(DOMAIN, {})

    # ส่งต่อให้แพลตฟอร์ม sensor ทำงาน (จะไปเรียกไฟล์ sensor.py)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry (เมื่อผู้ใช้กดลบ Integration)."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        # ลบข้อมูลที่เก็บไว้ออก
        pass

    return unload_ok