"""Sensor platform for Thai Electricity Bill."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
import homeassistant.util.dt as dt_util

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
    SensorDeviceClass,
)
from homeassistant.const import UnitOfEnergy
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.components.recorder import get_instance

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

SENSOR_TYPES = {
    "net_bill": {"name": "Net Bill", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:currency-thb"},
    "import_cost": {"name": "Imported Cost", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:cash-minus"},
    "export_income": {"name": "Exported Income", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:cash-plus"},
    "import_units": {"name": "Imported Units", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:transmission-tower-export"},
    "export_units": {"name": "Exported Units", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:transmission-tower-import"},
    "import_meter_previous": {"name": "Previous Import Meter", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:counter"},
    "export_meter_previous": {"name": "Previous Export Meter", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:counter"},
    "import_meter_current": {"name": "Current Import Meter", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:gauge"},
    "export_meter_current": {"name": "Current Export Meter", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:gauge"},
    "on_peak_units": {"name": "On Peak Units", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:lightning-bolt"},
    "off_peak_units": {"name": "Off Peak Units", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:lightning-bolt-outline"},
}

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = ElectricityBillCoordinator(hass, config_entry)
    await coordinator.async_setup()
    entities = []
    for st, si in SENSOR_TYPES.items():
        if not coordinator.energy_exported_id and "export" in st:
            continue
        # สร้าง entity TOU เฉพาะเมื่อเลือก Tariff แบบ TOU เท่านั้น
        if coordinator.tariff_type not in ["1.3.2", "1.2.2"] and st in ["on_peak_units", "off_peak_units"]:
            continue
        entities.append(ElectricityBillSensor(coordinator, st, si))
    async_add_entities(entities)

class ElectricityBillCoordinator:
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self.entry_id = config_entry.entry_id
        self.title = config_entry.title
        
        # เช็คว่ามีค่าจากการ Re-config ไหม ถ้ามีให้ใช้อันนั้น ถ้าไม่มีให้ใช้ค่าแรกตอนติดตั้ง
        config = config_entry.options if config_entry.options else config_entry.data
        
        self.provider = config_entry.data.get(CONF_PROVIDER) # การไฟฟ้า ไม่ให้เปลี่ยน
        self.tariff_type = config.get(CONF_TARIFF_TYPE)
        self.billing_date = config.get(CONF_BILLING_DATE, 14)
        self.ft_rate = config.get(CONF_FT_RATE, 0.1623)
        self.energy_imported_id = config.get(CONF_ENERGY_IMPORTED)
        self.energy_exported_id = config.get(CONF_ENERGY_EXPORTED)
        
        self.data = {k: 0.0 for k in SENSOR_TYPES.keys()}
        self.entities = []
        self._baseline_imported = None
        self._baseline_exported = None
        self._current_billing_period_start = None

    def register_entity(self, entity): self.entities.append(entity)

    async def async_setup(self):
        @callback
        def async_state_changed_listener(event): self.hass.async_create_task(self._async_process_update())
        track_entities = [self.energy_imported_id]
        if self.energy_exported_id: track_entities.append(self.energy_exported_id)
        async_track_state_change_event(self.hass, track_entities, async_state_changed_listener)
        await self._async_process_update()

    def _get_last_billing_date(self, now: datetime) -> datetime:
        target = now.replace(day=self.billing_date, hour=0, minute=0, second=0, microsecond=0)
        if target > now:
            last_month = (now.replace(day=1) - timedelta(days=1))
            try: target = last_month.replace(day=self.billing_date)
            except ValueError: target = last_month
        return target

    def _fetch_history_state(self, entity_id: str, target_dt: datetime) -> float | None:
        if not entity_id: return None
        from homeassistant.components.recorder import history
        target_dt_utc = dt_util.as_utc(target_dt)
        states = history.get_significant_states(self.hass, start_time=target_dt_utc - timedelta(seconds=1), end_time=target_dt_utc, entity_ids=[entity_id], include_start_time_state=True)
        if states and entity_id in states:
            for s in reversed(states[entity_id]):
                if s.state not in ("unknown", "unavailable"): return float(s.state)
        return None

    def _get_current_state_float(self, entity_id: str) -> float | None:
        # แก้ไข Bug: เช็คให้แน่ใจว่า entity_id ไม่เป็น None หรือค่าว่างก่อนไปดึงค่า
        if not entity_id: return None
        state = self.hass.states.get(entity_id)
        if state and state.state not in ("unknown", "unavailable"):
            try: return float(state.state)
            except ValueError: pass
        return None

    def _calculate_tou_units(self, entity_id: str, start_dt: datetime) -> tuple[float, float]:
        from homeassistant.components.recorder import history
        start_dt_utc = dt_util.as_utc(start_dt)
        now_utc = dt_util.utcnow()
        on_peak, off_peak = 0.0, 0.0
        states = history.get_significant_states(self.hass, start_time=start_dt_utc, end_time=now_utc, entity_ids=[entity_id])
        if entity_id not in states or not states[entity_id]: return 0.0, 0.0
        history_data = states[entity_id]
        for i in range(len(history_data) - 1):
            s1, s2 = history_data[i], history_data[i+1]
            try:
                diff = float(s2.state) - float(s1.state)
                if diff <= 0: continue
                dt = dt_util.as_local(s1.last_changed)
                if dt.weekday() < 5 and 9 <= dt.hour < 22: on_peak += diff
                else: off_peak += diff
            except (ValueError, TypeError): continue
        return on_peak, off_peak

    async def _async_update_baselines(self) -> None:
        target_dt = self._get_last_billing_date(dt_util.now())
        if self._current_billing_period_start == target_dt: return
        base_imp = await get_instance(self.hass).async_add_executor_job(self._fetch_history_state, self.energy_imported_id, target_dt)
        base_exp = await get_instance(self.hass).async_add_executor_job(self._fetch_history_state, self.energy_exported_id, target_dt)
        self._baseline_imported = base_imp if base_imp is not None else (self._get_current_state_float(self.energy_imported_id) or 0.0)
        self._baseline_exported = base_exp if base_exp is not None else (self._get_current_state_float(self.energy_exported_id) or 0.0)
        self._current_billing_period_start = target_dt

    async def _async_process_update(self) -> None:
        await self._async_update_baselines()
        cur_imp = self._get_current_state_float(self.energy_imported_id) or 0.0
        cur_exp = self._get_current_state_float(self.energy_exported_id) or 0.0
        imp_units = max(0, cur_imp - self._baseline_imported)
        exp_units = max(0, cur_exp - self._baseline_exported) if self.energy_exported_id else 0.0

        base_cost, service_charge = 0.0, 0.0
        
        if self.tariff_type in ["1.3.2", "1.2.2"]:
            on_units, off_units = await get_instance(self.hass).async_add_executor_job(self._calculate_tou_units, self.energy_imported_id, self._current_billing_period_start)
            base_cost = (on_units * 5.7982) + (off_units * 2.6369)
            service_charge = 24.62
            imp_units = on_units + off_units
            
            # เก็บค่าลงตัวแปรเพื่อให้ Entity เอาไปแสดงผล
            self.data["on_peak_units"] = round(on_units, 2)
            self.data["off_peak_units"] = round(off_units, 2)
        elif self.tariff_type in ["1.1", "1.1.1"]:
            if imp_units > 400: base_cost = (15*2.3488)+(10*2.9882)+(10*3.2405)+(65*3.6237)+(50*3.7171)+(250*4.2218)+((imp_units-400)*4.4217)
            elif imp_units > 150: base_cost = (15*2.3488)+(10*2.9882)+(10*3.2405)+(65*3.6237)+(50*3.7171)+((imp_units-150)*4.2218)
            elif imp_units > 100: base_cost = (15*2.3488)+(10*2.9882)+(10*3.2405)+(65*3.6237)+((imp_units-100)*3.7171)
            elif imp_units > 35: base_cost = (15*2.3488)+(10*2.9882)+(10*3.2405)+((imp_units-35)*3.6237)
            elif imp_units > 25: base_cost = (15*2.3488)+(10*2.9882)+((imp_units-25)*3.2405)
            elif imp_units > 15: base_cost = (15*2.3488)+((imp_units-15)*2.9882)
            else: base_cost = imp_units * 2.3488
            service_charge = 8.19
            self.data["on_peak_units"] = 0.0
            self.data["off_peak_units"] = 0.0
        elif self.tariff_type in ["1.2", "1.1.2"]:
            if imp_units > 400: base_cost = (150*3.2484)+(250*4.2218)+((imp_units-400)*4.4217)
            elif imp_units > 150: base_cost = (150*3.2484)+((imp_units-150)*4.2218)
            else: base_cost = imp_units * 3.2484
            service_charge = 24.62
            self.data["on_peak_units"] = 0.0
            self.data["off_peak_units"] = 0.0

        import_cost = ((base_cost + (service_charge if imp_units > 0 else 0) + (imp_units * self.ft_rate)) * 1.07)
        export_income = (exp_units * 2.20) * 0.99
        self.data.update({"import_units": round(imp_units, 2), "export_units": round(exp_units, 2), "import_cost": round(import_cost, 2), "export_income": round(export_income, 2), "net_bill": round(import_cost - export_income, 2), "import_meter_previous": round(self._baseline_imported, 2), "export_meter_previous": round(self._baseline_exported, 2), "import_meter_current": round(cur_imp, 2), "export_meter_current": round(cur_exp, 2)})
        for entity in self.entities: entity.async_write_ha_state()

class ElectricityBillSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL
    def __init__(self, coord, st, si):
        self.coordinator = coord
        self.sensor_type = st
        self._attr_name = si["name"]
        self._attr_unique_id = f"{coord.entry_id}_{st}"
        self._attr_device_class = si["device_class"]
        self._attr_native_unit_of_measurement = si["unit"]
        self._attr_icon = si["icon"]
        self._attr_device_info = {"identifiers": {(DOMAIN, coord.entry_id)}, "name": coord.title, "manufacturer": coord.provider, "model": f"Tariff Type {coord.tariff_type}"}
        coord.register_entity(self)
    @property
    def native_value(self): return self.coordinator.data.get(self.sensor_type)