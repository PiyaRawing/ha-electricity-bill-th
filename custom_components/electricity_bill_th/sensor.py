"""Sensor platform for Thai Electricity Bill."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
import homeassistant.util.dt as dt_util

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
)
from homeassistant.const import UnitOfEnergy, EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components.recorder import get_instance
from homeassistant.helpers.device_registry import DeviceInfo

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

# เซ็นเซอร์สำหรับการแสดงผล (จัดหมวดหมู่แล้ว)
SENSOR_TYPES = {
    # --- กลุ่มแสดงผลหลัก (ไม่ต้องใส่ category) ---
    "net_bill": {"name": "Net Bill", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:currency-thb"},
    "import_cost": {"name": "Imported Cost", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:cash-minus"},
    "export_income": {"name": "Exported Income", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:cash-plus"},
    "import_units": {"name": "Imported Units", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:transmission-tower-export"},
    "export_units": {"name": "Exported Units", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:transmission-tower-import"},
    "on_peak_units": {"name": "On Peak Units", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:lightning-bolt"},
    "off_peak_units": {"name": "Off Peak Units", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:lightning-bolt-outline"},
    
    # --- กลุ่มรายละเอียด/วินิจฉัย (ย้ายไปอยู่หมวด Diagnostic) ---
    "import_meter_previous": {"name": "Previous Import Meter", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:counter", "category": EntityCategory.DIAGNOSTIC},
    "export_meter_previous": {"name": "Previous Export Meter", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:counter", "category": EntityCategory.DIAGNOSTIC},
    "import_meter_current": {"name": "Current Import Meter", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:gauge", "category": EntityCategory.DIAGNOSTIC},
    "export_meter_current": {"name": "Current Export Meter", "device_class": SensorDeviceClass.ENERGY, "unit": UnitOfEnergy.KILO_WATT_HOUR, "icon": "mdi:gauge", "category": EntityCategory.DIAGNOSTIC},
    "on_peak_cost": {"name": "On Peak Cost", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:cash", "category": EntityCategory.DIAGNOSTIC},
    "off_peak_cost": {"name": "Off Peak Cost", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:cash", "category": EntityCategory.DIAGNOSTIC},
    "base_cost": {"name": "Base Cost", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:cash", "category": EntityCategory.DIAGNOSTIC},
    "service_charge": {"name": "Service Charge", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:cash", "category": EntityCategory.DIAGNOSTIC},
    "ft_cost": {"name": "Ft Cost", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:cash", "category": EntityCategory.DIAGNOSTIC},
    "total_before_vat": {"name": "Total Before VAT", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:cash", "category": EntityCategory.DIAGNOSTIC},
    "vat": {"name": "VAT", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:cash", "category": EntityCategory.DIAGNOSTIC},
    "export_income_before_tax": {"name": "Export Income Before Tax", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:cash-plus", "category": EntityCategory.DIAGNOSTIC},
    "export_tax": {"name": "Export Tax", "device_class": SensorDeviceClass.MONETARY, "unit": "THB", "icon": "mdi:cash-minus", "category": EntityCategory.DIAGNOSTIC},
}

async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = ElectricityBillCoordinator(hass, config_entry)
    await coordinator.async_setup()
    entities = []
    for st, si in SENSOR_TYPES.items():
        if not coordinator.energy_exported_id and "export" in st:
            continue
        if coordinator.tariff_type not in ["1.3.2", "1.2.2"] and st in ["on_peak_units", "off_peak_units", "on_peak_cost", "off_peak_cost"]:
            continue
        entities.append(ElectricityBillSensor(coordinator, st, si))
    async_add_entities(entities)

class ElectricityBillCoordinator:
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self.entry_id = config_entry.entry_id
        self.title = config_entry.title
        
        config = config_entry.options if config_entry.options else config_entry.data
        
        self.provider = config_entry.data.get(CONF_PROVIDER) 
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
        
        self._tou_history_loaded = False
        self._tou_on_peak = 0.0
        self._tou_off_peak = 0.0
        self._last_meter_val = None

    def register_entity(self, entity): 
        self.entities.append(entity)

    async def async_setup(self):
        @callback
        def async_timer_listener(now): 
            self.hass.async_create_task(self.async_update())
            
        async_track_time_interval(self.hass, async_timer_listener, timedelta(minutes=5))
        await self.async_update()

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
        if not entity_id: return None
        state = self.hass.states.get(entity_id)
        if state and state.state not in ("unknown", "unavailable"):
            try: return float(state.state)
            except ValueError: pass
        return None

    def _calculate_tou_units_history(self, entity_id: str, start_dt: datetime, end_dt: datetime) -> tuple[float, float]:
        from homeassistant.components.recorder import history
        start_dt_utc = dt_util.as_utc(start_dt)
        end_dt_utc = dt_util.as_utc(end_dt)
        on_peak, off_peak = 0.0, 0.0
        states = history.get_significant_states(self.hass, start_time=start_dt_utc, end_time=end_dt_utc, entity_ids=[entity_id])
        if entity_id not in states or not states[entity_id]: return 0.0, 0.0
        history_data = states[entity_id]
        
        for i in range(len(history_data) - 1):
            s1, s2 = history_data[i], history_data[i+1]
            try:
                diff = float(s2.state) - float(s1.state)
                if diff <= 0: continue
                dt = dt_util.as_local(s2.last_changed)
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
        self._tou_history_loaded = False 

    async def async_update(self) -> None:
        await self._async_update_baselines()
        
        cur_imp = self._get_current_state_float(self.energy_imported_id) or 0.0
        cur_exp = self._get_current_state_float(self.energy_exported_id) or 0.0
        
        imp_units = max(0, cur_imp - self._baseline_imported)
        exp_units = max(0, cur_exp - self._baseline_exported) if self.energy_exported_id else 0.0

        base_cost, service_charge = 0.0, 0.0
        
        if self.tariff_type in ["1.3.2", "1.2.2"]:
            if not self._tou_history_loaded:
                on_u, off_u = await get_instance(self.hass).async_add_executor_job(
                    self._calculate_tou_units_history, self.energy_imported_id, self._current_billing_period_start, dt_util.now()
                )
                self._tou_on_peak = on_u
                self._tou_off_peak = off_u
                self._tou_history_loaded = True
                self._last_meter_val = cur_imp
            else:
                if self._last_meter_val is not None and cur_imp > self._last_meter_val:
                    diff = cur_imp - self._last_meter_val
                    now_local = dt_util.now()
                    if now_local.weekday() < 5 and 9 <= now_local.hour < 22:
                        self._tou_on_peak += diff
                    else:
                        self._tou_off_peak += diff
                self._last_meter_val = cur_imp
                
            on_cost = self._tou_on_peak * 5.7982
            off_cost = self._tou_off_peak * 2.6369
            base_cost = on_cost + off_cost
            service_charge = 24.62
            
            imp_units = self._tou_on_peak + self._tou_off_peak
            self.data["on_peak_units"] = round(self._tou_on_peak, 2)
            self.data["off_peak_units"] = round(self._tou_off_peak, 2)
            self.data["on_peak_cost"] = round(on_cost, 2)
            self.data["off_peak_cost"] = round(off_cost, 2)
            
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
            self.data["on_peak_cost"] = 0.0
            self.data["off_peak_cost"] = 0.0
        elif self.tariff_type in ["1.2", "1.1.2"]:
            if imp_units > 400: base_cost = (150*3.2484)+(250*4.2218)+((imp_units-400)*4.4217)
            elif imp_units > 150: base_cost = (150*3.2484)+((imp_units-150)*4.2218)
            else: base_cost = imp_units * 3.2484
            service_charge = 24.62
            self.data["on_peak_units"] = 0.0
            self.data["off_peak_units"] = 0.0
            self.data["on_peak_cost"] = 0.0
            self.data["off_peak_cost"] = 0.0

        actual_service_charge = service_charge if imp_units > 0 else 0.0
        ft_cost = imp_units * self.ft_rate
        total_before_vat = base_cost + actual_service_charge + ft_cost
        vat_cost = total_before_vat * 0.07
        import_cost = total_before_vat + vat_cost

        export_before_tax = exp_units * 2.20
        export_tax = export_before_tax * 0.01  
        export_income = export_before_tax - export_tax

        self.data.update({
            "import_units": round(imp_units, 2), 
            "export_units": round(exp_units, 2), 
            "import_cost": round(import_cost, 2), 
            "export_income": round(export_income, 2), 
            "net_bill": round(import_cost - export_income, 2), 
            "import_meter_previous": round(self._baseline_imported, 2), 
            "export_meter_previous": round(self._baseline_exported, 2), 
            "import_meter_current": round(cur_imp, 2), 
            "export_meter_current": round(cur_exp, 2),
            "base_cost": round(base_cost, 2),
            "service_charge": round(actual_service_charge, 2),
            "ft_cost": round(ft_cost, 2),
            "total_before_vat": round(total_before_vat, 2),
            "vat": round(vat_cost, 2),
            "export_income_before_tax": round(export_before_tax, 2),
            "export_tax": round(export_tax, 2),
        })
        for entity in self.entities: 
            entity.async_write_ha_state()

class ElectricityBillSensor(SensorEntity):
    """Representation of an Electricity Bill Sensor."""

    def __init__(self, coordinator: ElectricityBillCoordinator, sensor_type: str, sensor_info: dict):
        self.coordinator = coordinator
        self._type = sensor_type
        self._attr_name = f"{coordinator.title} {sensor_info['name']}"
        self._attr_unique_id = f"{coordinator.entry_id}_{sensor_type}"
        self._attr_device_class = sensor_info.get("device_class")
        self._attr_native_unit_of_measurement = sensor_info.get("unit")
        self._attr_icon = sensor_info.get("icon")
        self._attr_entity_category = sensor_info.get("category")
        
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=coordinator.title,
            manufacturer="Thai Electricity Bill",
            model=coordinator.provider,
        )

    async def async_added_to_hass(self) -> None:
        self.coordinator.register_entity(self)

    @property
    def should_poll(self) -> bool:
        return False

    @property
    def native_value(self):
        return self.coordinator.data.get(self._type)

    @property
    def extra_state_attributes(self):
        return {
            "provider": self.coordinator.provider,
            "tariff_type": self.coordinator.tariff_type,
            "billing_date": self.coordinator.billing_date, # เพิ่มส่งค่า billing_date ให้หน้ากาก
        }

    async def async_update(self) -> None:
        await self.coordinator.async_update()