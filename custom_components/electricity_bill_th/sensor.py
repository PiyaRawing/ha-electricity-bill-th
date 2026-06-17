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

# รูปแบบของ Sensor ทั้ง 9 ตัว
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
}

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = ElectricityBillCoordinator(hass, config_entry)
    await coordinator.async_setup()

    entities = []
    for sensor_type, sensor_info in SENSOR_TYPES.items():
        # ถ้าไม่มีการตั้งค่า export ไม่ต้องสร้าง entity ที่เกี่ยวกับ export
        if not coordinator.energy_exported_id and "export" in sensor_type:
            continue
        entities.append(ElectricityBillSensor(coordinator, sensor_type, sensor_info))
    
    async_add_entities(entities)


class ElectricityBillCoordinator:
    """Class สำหรับดึงข้อมูลและคำนวณรวดเดียว แล้วแจกจ่ายให้ Entity ทั้งหมด"""
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.hass = hass
        self.entry_id = config_entry.entry_id
        self.title = config_entry.title
        self.provider = config_entry.data.get(CONF_PROVIDER)
        self.tariff_type = config_entry.data.get(CONF_TARIFF_TYPE)
        self.billing_date = config_entry.data.get(CONF_BILLING_DATE, 14)
        self.ft_rate = config_entry.data.get(CONF_FT_RATE, 0.1623)
        self.energy_imported_id = config_entry.data.get(CONF_ENERGY_IMPORTED)
        self.energy_exported_id = config_entry.data.get(CONF_ENERGY_EXPORTED)
        
        self.data = {k: 0.0 for k in SENSOR_TYPES.keys()}
        self.entities = []
        
        self._baseline_imported: float | None = None
        self._baseline_exported: float | None = None
        self._current_billing_period_start: datetime | None = None
        self._unsub_track = None

    def register_entity(self, entity: ElectricityBillSensor):
        self.entities.append(entity)

    async def async_setup(self):
        """เริ่มดักฟังการเปลี่ยนแปลงของ Sensor"""
        @callback
        def async_state_changed_listener(event):
            self.hass.async_create_task(self._async_process_update())

        track_entities = [self.energy_imported_id]
        if self.energy_exported_id:
            track_entities.append(self.energy_exported_id)

        self._unsub_track = async_track_state_change_event(
            self.hass, track_entities, async_state_changed_listener
        )
        await self._async_process_update()

    def _get_last_billing_date(self, now: datetime) -> datetime:
        try:
            target = now.replace(day=self.billing_date, hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            import calendar
            last_day = calendar.monthrange(now.year, now.month)[1]
            target = now.replace(day=last_day, hour=0, minute=0, second=0, microsecond=0)

        if target > now:
            first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_month = first_day - timedelta(days=1)
            try:
                target = last_month.replace(day=self.billing_date)
            except ValueError:
                target = last_month
        return target

    def _fetch_history_state(self, entity_id: str, target_dt: datetime) -> float | None:
        if not entity_id:
            return None
        try:
            from homeassistant.components.recorder import history
            import homeassistant.util.dt as dt_util

            # แปลงเวลาเป้าหมายเป็น UTC ตามมาตรฐานที่ Recorder ใช้
            target_dt_utc = dt_util.as_utc(target_dt)
            
            # ดึงประวัติด้วยฟังก์ชันของ HA เวอร์ชั่นใหม่ (get_significant_states)
            # ตั้งค่า include_start_time_state=True เพื่อให้มันดึงค่าล่าสุด ณ เวลานั้นมาให้เลย
            start_time = target_dt_utc - timedelta(seconds=1)
            
            states = history.get_significant_states(
                self.hass, 
                start_time=start_time, 
                end_time=target_dt_utc, 
                entity_ids=[entity_id],
                include_start_time_state=True,
                significant_changes_only=False
            )
            
            if states and entity_id in states and states[entity_id]:
                # หาค่าที่สมบูรณ์ (ไม่ใช่ unknown/unavailable) โดยไล่จากข้อมูลล่าสุด
                for state in reversed(states[entity_id]):
                    if state.state not in ("unknown", "unavailable"):
                        try:
                            return float(state.state)
                        except ValueError:
                            continue
                            
        except Exception as e:
            _LOGGER.error("Error fetching history for %s: %s", entity_id, e)
            
        return None

    def _get_current_state_float(self, entity_id: str) -> float | None:
        if not entity_id: return None
        state = self.hass.states.get(entity_id)
        if state and state.state not in ("unknown", "unavailable"):
            try: return float(state.state)
            except ValueError: pass
        return None

    async def _async_update_baselines(self) -> None:
        now = dt_util.now()
        target_dt = self._get_last_billing_date(now)
        
        if self._current_billing_period_start == target_dt and self._baseline_imported is not None:
            return
            
        base_imp = await self.hass.async_add_executor_job(self._fetch_history_state, self.energy_imported_id, target_dt)
        base_exp = await self.hass.async_add_executor_job(self._fetch_history_state, self.energy_exported_id, target_dt)

        self._baseline_imported = base_imp if base_imp is not None else (self._get_current_state_float(self.energy_imported_id) or 0.0)
        self._baseline_exported = base_exp if base_exp is not None else (self._get_current_state_float(self.energy_exported_id) or 0.0)
        self._current_billing_period_start = target_dt

    async def _async_process_update(self) -> None:
        await self._async_update_baselines()
        
        current_imp = self._get_current_state_float(self.energy_imported_id) or 0.0
        current_exp = self._get_current_state_float(self.energy_exported_id) or 0.0

        imp_units = current_imp - self._baseline_imported
        if imp_units < 0: imp_units = current_imp

        exp_units = current_exp - self._baseline_exported
        if exp_units < 0: exp_units = current_exp
        if not self.energy_exported_id: exp_units = 0.0

        # --- คำนวณค่าไฟ ---
        base_cost = 0.0
        if imp_units > 400:
            base_cost = (150 * 3.2484) + (250 * 4.2218) + ((imp_units - 400) * 4.4217)
        elif imp_units > 150:
            base_cost = (150 * 3.2484) + ((imp_units - 150) * 4.2218)
        elif imp_units > 0:
            base_cost = (imp_units * 3.2484)

        # เลือกค่าบริการรายเดือนตามผู้ให้บริการ
        service_charge_rate = 38.22 if self.provider == "PEA" else 24.62
        service_charge = service_charge_rate if imp_units > 0 else 0.0
        
        ft_cost = imp_units * self.ft_rate
        total_import_pre_vat = base_cost + service_charge + ft_cost
        import_cost = total_import_pre_vat * 1.07

        # --- คำนวณค่าขายไฟ ---
        export_income_pre_tax = exp_units * 2.20
        export_income = export_income_pre_tax * 0.99

        # --- อัปเดตข้อมูลทั้งหมด ---
        self.data["import_units"] = round(imp_units, 2)
        self.data["export_units"] = round(exp_units, 2)
        self.data["import_cost"] = round(import_cost, 2)
        self.data["export_income"] = round(export_income, 2)
        self.data["net_bill"] = round(import_cost - export_income, 2)
        
        # เพิ่มข้อมูลมิเตอร์
        self.data["import_meter_previous"] = round(self._baseline_imported, 2)
        self.data["export_meter_previous"] = round(self._baseline_exported, 2)
        self.data["import_meter_current"] = round(current_imp, 2)
        self.data["export_meter_current"] = round(current_exp, 2)

        for entity in self.entities:
            entity.async_write_ha_state()


class ElectricityBillSensor(SensorEntity):
    """Sensor แต่ละตัว"""
    _attr_has_entity_name = True
    _attr_state_class = SensorStateClass.TOTAL

    def __init__(self, coordinator: ElectricityBillCoordinator, sensor_type: str, sensor_info: dict):
        self.coordinator = coordinator
        self.sensor_type = sensor_type
        
        self._attr_name = sensor_info["name"]
        self._attr_unique_id = f"{coordinator.entry_id}_{sensor_type}"
        self._attr_device_class = sensor_info["device_class"]
        self._attr_native_unit_of_measurement = sensor_info["unit"]
        self._attr_icon = sensor_info["icon"]

        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry_id)},
            "name": coordinator.title,
            "manufacturer": coordinator.provider,
            "model": f"Tariff Type {coordinator.tariff_type}",
        }
        coordinator.register_entity(self)

    @property
    def native_value(self) -> float | None:
        return self.coordinator.data.get(self.sensor_type)