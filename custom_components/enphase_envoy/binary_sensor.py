from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import COORDINATOR, DOMAIN, NAME, ICON, BINARY_SENSORS


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
                    device_name = f"{sensor_description.name} {relay}"
                    entity_name = f"{name} {device_name}"

                    serial_number = relay
                    entities.append(
                        EnvoyRelayEntity(
                            sensor_description,
                            entity_name,
                            device_name,
                            serial_number,
                            serial_number,
                            coordinator,
                            config_entry.unique_id,
                        )
                    )

        elif sensor_description.key == "firmware":
            if coordinator.data.get("update_status") is not None:
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
    def icon(self):
        """Icon to use in the frontend, if any."""
        return ICON

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
        return DeviceInfo(
            identifiers={(DOMAIN, str(self._device_serial_number))},
            manufacturer="Enphase",
            model="Envoy",
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
    def icon(self):
        """Icon to use in the frontend, if any."""
        return ICON

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
        return DeviceInfo(
            identifiers={(DOMAIN, str(self._device_serial_number))},
            manufacturer="Enphase",
            model="Envoy",
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
    def icon(self):
        """Icon to use in the frontend, if any."""
        return ICON

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

        if self.MODEL == "Relay":
            info = self.coordinator.data.get("relay_info", {}).get(
                self._device_serial_number, {}
            )
            device_info_kw["sw_version"] = info.get("img_pnum_running", None)
            device_info_kw["hw_version"] = info.get("part_num", None)

        return DeviceInfo(
            identifiers={(DOMAIN, str(self._device_serial_number))},
            manufacturer="Enphase",
            model=self.MODEL,
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
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        relays = self.coordinator.data.get("relays")
        if relays is None:
            return None

        return relays.get(self._serial_number).get("relay") == "closed"

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return the state attributes."""
        if self.coordinator.data.get("relays") is not None:
            relay = self.coordinator.data.get("relays").get(self._serial_number)
            return {
                "last_reported": relay.get("report_date"),
                "reason_code": relay.get("reason_code"),
                "reason": relay.get("reason"),
            }

        return None
