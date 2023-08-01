from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    COORDINATOR,
    DOMAIN,
    NAME,
    BINARY_SENSORS,
    resolve_hardware_id,
    get_model_name,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = data[COORDINATOR]
    name = data[NAME]

    entities = []
    for sensor_description in BINARY_SENSORS:
        if sensor_description.key.startswith("inverters_"):
            if coordinator.data.get("inverters_status") is not None:
                for inverter in coordinator.data["inverters_status"].keys():
                    device_name = f"Inverter {inverter}"
                    entity_name = f"{device_name} {sensor_description.name}"
                    entities.append(
                        EnvoyInverterEntity(
                            sensor_description,
                            entity_name,
                            device_name,
                            inverter,
                            None,
                            coordinator,
                        )
                    )
        elif sensor_description.key == "grid_status":
            if coordinator.data.get("grid_status") is not None:
                entities.append(
                    EnvoyGridStatusEntity(
                        sensor_description,
                        sensor_description.name,
                        name,
                        config_entry.unique_id,
                        None,
                        coordinator,
                    )
                )

        elif sensor_description.key == "relays":
            if coordinator.data.get("relays") is not None:
                for relay in coordinator.data["relays"]:
                    device_name = f"Relay {relay}"
                    entity_name = f"{device_name} {sensor_description.name}"

                    serial_number = relay
                    entities.append(
                        EnvoyRelayContactEntity(
                            sensor_description,
                            entity_name,
                            device_name,
                            serial_number,
                            serial_number,
                            coordinator,
                            config_entry.unique_id,
                        )
                    )

        elif sensor_description.key.startswith("relays_"):
            sensor_key = sensor_description.key.split("_", 1)[-1]
            if coordinator.data.get("relays") != None:
                for serial_number, data in coordinator.data["relays"].items():
                    if data.get(sensor_key, None) == None:
                        continue

                    device_name = f"Relay {serial_number}"
                    entity_name = f"{device_name} {sensor_description.name}"

                    entities.append(
                        EnvoyRelayGenericEntity(
                            sensor_description,
                            entity_name,
                            device_name,
                            serial_number,
                            None,
                            coordinator,
                            config_entry.unique_id,
                        )
                    )

        elif sensor_description.key == "firmware":
            if coordinator.data.get("envoy_info", {}).get("update_status") is not None:
                entity_name = f"{name} {sensor_description.name}"
                serial_number = name.split(None, 1)[-1]
                entities.append(
                    EnvoyFirmwareEntity(
                        sensor_description,
                        entity_name,
                        name,
                        config_entry.unique_id,
                        serial_number,
                        coordinator,
                    )
                )

    async_add_entities(entities)


class EnvoyGridStatusEntity(CoordinatorEntity, BinarySensorEntity):
    def __init__(
        self,
        description,
        name,
        device_name,
        device_serial_number,
        serial_number,
        coordinator,
    ):
        self.entity_description = description
        self._name = name
        self._serial_number = serial_number
        self._device_name = device_name
        self._device_serial_number = device_serial_number
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
    def device_info(self) -> DeviceInfo or None:
        """Return the device_info of the device."""
        if not self._device_serial_number:
            return None

        model = self.coordinator.data.get("envoy_info", {}).get("model", "Standard")

        return DeviceInfo(
            identifiers={(DOMAIN, str(self._device_serial_number))},
            manufacturer="Enphase",
            model=f"Envoy-S {model}",
            name=self._device_name,
        )

    @property
    def is_on(self) -> bool:
        """Return the status of the requested attribute."""
        return self.coordinator.data.get("grid_status") == "closed"


class EnvoyInverterEntity(CoordinatorEntity, BinarySensorEntity):
    def __init__(
        self,
        description,
        name,
        device_name,
        device_serial_number,
        serial_number,
        coordinator,
    ):
        self.entity_description = description
        self._name = name
        self._serial_number = serial_number
        self._device_name = device_name
        self._device_serial_number = device_serial_number
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
    def extra_state_attributes(self):
        """Return the state attributes."""
        if self.coordinator.data.get("inverters_status") is not None:
            value = (
                self.coordinator.data.get("inverters_status")
                .get(self._device_serial_number)
                .get("report_date")
            )
            return {"last_reported": value}

        return None

    @property
    def device_info(self) -> DeviceInfo or None:
        """Return the device_info of the device."""
        if not self._device_serial_number:
            return None

        hw_version = (
            self.coordinator.data.get("inverters_info", {})
            .get(self._device_serial_number, {})
            .get("part_num", None)
        )
        return DeviceInfo(
            identifiers={(DOMAIN, str(self._device_serial_number))},
            manufacturer="Enphase",
            model=get_model_name("Inverter", hw_version),
            name=self._device_name,
        )

    @property
    def is_on(self) -> bool:
        """Return the status of the requested attribute."""
        if self.coordinator.data.get("inverters_status") is not None:
            return (
                self.coordinator.data.get("inverters_status")
                .get(self._device_serial_number)
                .get(self.entity_description.key[10:])
            )


class EnvoyBaseEntity(CoordinatorEntity):
    """Envoy entity"""

    MODEL = "Envoy"

    def __init__(
        self,
        description,
        name,
        device_name,
        device_serial_number,
        serial_number,
        coordinator,
        parent_device=None,
    ):
        """Initialize Envoy entity."""
        self.entity_description = description
        self._name = name
        self._serial_number = serial_number
        self._device_name = device_name
        self._device_serial_number = device_serial_number
        self._parent_device = parent_device

        super().__init__(coordinator)

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
        return self.coordinator.data.get(self.entity_description.key)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the device_info of the device."""
        if not self._device_serial_number:
            return None
        device_info_kw = {}
        if self._parent_device:
            device_info_kw["via_device"] = (DOMAIN, self._parent_device)

        model_name = self.MODEL
        if self.MODEL == "Envoy":
            model = self.coordinator.data.get("envoy_info", {}).get("model", "Standard")
            model_name = f"Envoy-S {model}"

        elif self.MODEL == "Relay":
            info = self.coordinator.data.get("relay_info", {}).get(
                self._device_serial_number, {}
            )
            device_info_kw["sw_version"] = info.get("img_pnum_running", None)
            device_info_kw["hw_version"] = resolve_hardware_id(
                info.get("part_num", None)
            )
            model_name = get_model_name(model_name, info.get("part_num", None))

        return DeviceInfo(
            identifiers={(DOMAIN, str(self._device_serial_number))},
            manufacturer="Enphase",
            model=model_name,
            name=self._device_name,
            **device_info_kw,
        )


class EnvoyBinaryEntity(EnvoyBaseEntity, BinarySensorEntity):
    def __init__(
        self,
        description,
        name,
        device_name,
        device_serial_number,
        serial_number,
        coordinator,
        parent_device=None,
    ):
        super().__init__(
            description=description,
            name=name,
            device_name=device_name,
            device_serial_number=device_serial_number,
            serial_number=serial_number,
            coordinator=coordinator,
            parent_device=parent_device,
        )


class EnvoyFirmwareEntity(EnvoyBinaryEntity):
    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if self.coordinator.data.get("envoy_info"):
            update_status = self.coordinator.data.get("envoy_info").get("update_status")
            return update_status != "satisfied"
        return False

    @property
    def extra_state_attributes(self) -> None:
        return None


class EnvoyRelayEntity(EnvoyBinaryEntity):
    """Envoy relay entity."""

    MODEL = "Relay"

    @property
    def relay(self):
        return self.coordinator.data.get("relays", {}).get(
            self._device_serial_number, {}
        )

    @property
    def value_key(self):
        if "_" in self.entity_description.key:
            return self.entity_description.key.split("_", 1)[-1]
        return self.entity_description.key

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        if self.value_key != "communicating":
            return self.relay.get("communicating")

        return True

    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if self.relay is None:
            return None

        return self.relay.get("relay") == "closed"

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return the state attributes."""
        if self.relay is None:
            return None

        return {
            "last_reported": self.relay.get("report_date"),
            "reason_code": self.relay.get("reason_code"),
            "reason": self.relay.get("reason"),
        }


class EnvoyRelayContactEntity(EnvoyRelayEntity):
    @property
    def icon(self):
        return "mdi:electric-switch-closed" if self.is_on else "mdi:electric-switch"


class EnvoyRelayGenericEntity(EnvoyRelayEntity):
    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if self.relay is None:
            return None

        return self.relay.get(self.value_key)

    @property
    def extra_state_attributes(self) -> dict | None:
        return None
