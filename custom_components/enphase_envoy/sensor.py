"""Support for Enphase Envoy solar energy monitor."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, CONF_HOST
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    COORDINATOR,
    DOMAIN,
    NAME,
    SENSORS,
    PHASE_SENSORS,
    LIVE_UPDATEABLE_ENTITIES,
    ENABLE_ADDITIONAL_METRICS,
    ADDITIONAL_METRICS,
    BATTERY_STATE_MAPPING,
    resolve_hardware_id,
    get_model_name,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up envoy sensor platform."""
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = data[COORDINATOR]
    name = data[NAME]
    live_entities = data[LIVE_UPDATEABLE_ENTITIES]
    options = config_entry.options

    entities = []
    for sensor_description in SENSORS:
        if not options.get(ENABLE_ADDITIONAL_METRICS, False):
            if sensor_description.key in ADDITIONAL_METRICS:
                continue

        if sensor_description.key == "inverters":
            if coordinator.data.get("inverters_production") is not None:
                for inverter in coordinator.data["inverters_production"]:
                    device_name = f"Inverter {inverter}"
                    entity_name = f"{device_name} {sensor_description.name}"
                    serial_number = inverter
                    entities.append(
                        EnvoyInverterEntity(
                            sensor_description,
                            entity_name,
                            device_name,
                            serial_number,
                            serial_number,
                            coordinator,
                            config_entry.unique_id,
                        )
                    )
        elif sensor_description.key.startswith("inverters_"):
            if coordinator.data.get("inverters_status") is not None:
                for inverter in coordinator.data["inverters_status"].keys():
                    device_name = f"Inverter {inverter}"
                    entity_name = f"{device_name} {sensor_description.name}"
                    serial_number = inverter
                    entities.append(
                        EnvoyInverterEntity(
                            sensor_description,
                            entity_name,
                            device_name,
                            serial_number,
                            None,
                            coordinator,
                            config_entry.unique_id,
                        )
                    )

        elif sensor_description.key.startswith("batteries_"):
            if coordinator.data.get("batteries") is not None:
                for battery in coordinator.data["batteries"].keys():
                    device_name = f"Battery {battery}"
                    entity_name = f"{device_name} {sensor_description.name}"
                    serial_number = battery
                    entities.append(
                        EnvoyBatteryEntity(
                            sensor_description,
                            entity_name,
                            device_name,
                            serial_number,
                            None,
                            coordinator,
                            config_entry.unique_id,
                        )
                    )

        elif sensor_description.key.startswith("agg_batteries_"):
            if coordinator.data.get("batteries") is not None:
                entity_name = f"{name} {sensor_description.name}"
                entities.append(
                    CoordinatedEnvoyEntity(
                        sensor_description,
                        entity_name,
                        name,
                        config_entry.unique_id,
                        None,
                        coordinator,
                        config_entry.data[CONF_HOST],
                    )
                )

        else:
            data = coordinator.data.get(sensor_description.key)
            if data is None:
                continue

            entity_name = f"{name} {sensor_description.name}"
            entities.append(
                CoordinatedEnvoyEntity(
                    sensor_description,
                    entity_name,
                    name,
                    config_entry.unique_id,
                    None,
                    coordinator,
                    config_entry.data[CONF_HOST],
                )
            )

    for sensor_description in PHASE_SENSORS:
        if not options.get(ENABLE_ADDITIONAL_METRICS, False):
            if sensor_description.key in ADDITIONAL_METRICS:
                continue

        data = coordinator.data.get(sensor_description.key)
        if data is None:
            continue

        entity_name = f"{name} {sensor_description.name}"
        live_entities[sensor_description.key] = CoordinatedEnvoyEntity(
            sensor_description,
            entity_name,
            name,
            config_entry.unique_id,
            None,
            coordinator,
            config_entry.data[CONF_HOST],
        )
        entities.append(live_entities[sensor_description.key])

    async_add_entities(entities)


class EnvoyEntity(SensorEntity):
    """Envoy entity"""

    def __init__(
        self,
        description,
        name,
        device_name,
        device_serial_number,
        serial_number,
    ):
        """Initialize Envoy entity."""
        self.entity_description = description
        self._name = name
        self._serial_number = serial_number
        self._device_name = device_name
        self._device_serial_number = device_serial_number

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique id of the sensor."""
        if self._serial_number:
            return self._serial_number
        if self._device_serial_number:
            return f"{self._device_serial_number}_{self.entity_description.key}"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return None


class CoordinatedEnvoyEntity(EnvoyEntity, CoordinatorEntity):
    def __init__(
        self,
        description,
        name,
        device_name,
        device_serial_number,
        serial_number,
        coordinator,
        device_host,
    ):
        EnvoyEntity.__init__(
            self, description, name, device_name, device_serial_number, serial_number
        )
        CoordinatorEntity.__init__(self, coordinator)
        self.device_host = device_host

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get(self.entity_description.key)

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the device_info of the device."""
        if not self._device_serial_number:
            return None

        sw_version = self.coordinator.data.get("envoy_info", {}).get("software", None)
        hw_version = self.coordinator.data.get("envoy_info", {}).get("pn", None)
        model = self.coordinator.data.get("envoy_info", {}).get("model", "Standard")

        return DeviceInfo(
            identifiers={(DOMAIN, str(self._device_serial_number))},
            manufacturer="Enphase",
            model=f"Envoy-S {model}",
            name=self._device_name,
            sw_version=sw_version,
            hw_version=resolve_hardware_id(hw_version),
            configuration_url=(
                f"https://{self.device_host}/" if self.device_host else None
            ),
        )


class EnvoyInverterEntity(CoordinatorEntity, SensorEntity):
    """Envoy inverter entity."""

    def __init__(
        self,
        description,
        name,
        device_name,
        device_serial_number,
        serial_number,
        coordinator,
        parent_device,
    ):
        self.entity_description = description
        self._name = name
        self._serial_number = serial_number
        self._device_name = device_name
        self._device_serial_number = device_serial_number
        self._parent_device = parent_device
        CoordinatorEntity.__init__(self, coordinator)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique id of the sensor."""
        if self._serial_number:
            return self._serial_number
        if self._device_serial_number:
            return f"{self._device_serial_number}_{self.entity_description.key}"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.entity_description.key.startswith("inverters_"):
            if self.coordinator.data.get("inverters_status") is not None:
                return (
                    self.coordinator.data.get("inverters_status")
                    .get(self._device_serial_number)
                    .get(self.entity_description.key[10:])
                )
        elif self.coordinator.data.get("inverters_production") is not None:
            return (
                self.coordinator.data.get("inverters_production")
                .get(self._device_serial_number)
                .get("watt")
            )

        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self.entity_description.key.startswith("inverters_"):
            if self.coordinator.data.get("inverters_status") is not None:
                value = (
                    self.coordinator.data.get("inverters_status")
                    .get(self._device_serial_number)
                    .get("report_date")
                )
                return {"last_reported": value}
        elif self.coordinator.data.get("inverters_production") is not None:
            value = (
                self.coordinator.data.get("inverters_production")
                .get(self._serial_number)
                .get("report_date")
            )
            return {"last_reported": value}

        return None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the device_info of the device."""
        if not self._device_serial_number:
            return None

        sw_version = None
        hw_version = None
        if self.coordinator.data.get("inverters_info") and self.coordinator.data.get(
            "inverters_info"
        ).get(self._device_serial_number):
            sw_version = (
                self.coordinator.data.get("inverters_info")
                .get(self._device_serial_number)
                .get("img_pnum_running")
            )
            hw_version = (
                self.coordinator.data.get("inverters_info")
                .get(self._device_serial_number)
                .get("part_num")
            )

        return DeviceInfo(
            identifiers={(DOMAIN, str(self._device_serial_number))},
            manufacturer="Enphase",
            model=get_model_name("Inverter", hw_version),
            name=self._device_name,
            via_device=(DOMAIN, self._parent_device),
            sw_version=sw_version,
            hw_version=resolve_hardware_id(hw_version),
        )


class EnvoyBatteryEntity(CoordinatorEntity, SensorEntity):
    """Envoy battery entity."""

    def __init__(
        self,
        description,
        name,
        device_name,
        device_serial_number,
        serial_number,
        coordinator,
        parent_device,
    ):
        self.entity_description = description
        self._name = name
        self._serial_number = serial_number
        self._device_name = device_name
        self._device_serial_number = device_serial_number
        self._parent_device = parent_device
        CoordinatorEntity.__init__(self, coordinator)

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def unique_id(self):
        """Return the unique id of the sensor."""
        if self._serial_number:
            return self._serial_number
        if self._device_serial_number:
            return f"{self._device_serial_number}_{self.entity_description.key}"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.coordinator.data.get("batteries") is not None:
            if self.entity_description.key == "batteries_power":
                return int(
                    self.coordinator.data.get("batteries_power")
                    .get(self._device_serial_number)
                    .get("real_power_mw")
                    / 1000
                )
            elif self.entity_description.key == "batteries_led_status":
                return BATTERY_STATE_MAPPING.get(
                    self.coordinator.data.get("batteries")
                    .get(self._device_serial_number)
                    .get("led_status")
                )
            else:
                return (
                    self.coordinator.data.get("batteries")
                    .get(self._device_serial_number)
                    .get(self.entity_description.key[10:])
                )

        return None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self.coordinator.data.get("batteries") is not None:
            battery = self.coordinator.data.get("batteries").get(
                self._device_serial_number
            )
            return {"last_reported": battery.get("report_date")}

        return None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the device_info of the device."""
        if not self._device_serial_number:
            return None

        sw_version = None
        hw_version = None
        if self.coordinator.data.get("batteries") and self.coordinator.data.get(
            "batteries"
        ).get(self._device_serial_number):
            sw_version = (
                self.coordinator.data.get("batteries")
                .get(self._device_serial_number)
                .get("img_pnum_running")
            )
            hw_version = (
                self.coordinator.data.get("batteries")
                .get(self._device_serial_number)
                .get("part_num")
            )

        return DeviceInfo(
            identifiers={(DOMAIN, str(self._device_serial_number))},
            manufacturer="Enphase",
            model=get_model_name("Battery", hw_version),
            name=self._device_name,
            via_device=(DOMAIN, self._parent_device),
            sw_version=sw_version,
            hw_version=resolve_hardware_id(hw_version),
        )
