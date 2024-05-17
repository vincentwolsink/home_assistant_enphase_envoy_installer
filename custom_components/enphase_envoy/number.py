from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.number import NumberEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    COORDINATOR,
    DOMAIN,
    NAME,
    READER,
    STORAGE_RESERVE_SOC_NUMBER,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][config_entry.entry_id]
    coordinator = data[COORDINATOR]
    name = data[NAME]
    reader = data[READER]

    entities = []
    if (
        coordinator.data.get("batteries") is not None
        and coordinator.data.get("storage_charge_from_grid") is not None
    ):
        entities.append(
            EnvoyStorageReservedSocEntity(
                STORAGE_RESERVE_SOC_NUMBER,
                STORAGE_RESERVE_SOC_NUMBER.name,
                name,
                config_entry.unique_id,
                None,
                coordinator,
                reader,
            )
        )
    async_add_entities(entities)


class EnvoyNumberEntity(CoordinatorEntity, NumberEntity):
    def __init__(
        self,
        description,
        name,
        device_name,
        device_serial_number,
        serial_number,
        coordinator,
        reader,
    ):
        self.entity_description = description
        self._name = name
        self._serial_number = serial_number
        self._device_name = device_name
        self._device_serial_number = device_serial_number
        CoordinatorEntity.__init__(self, coordinator)
        self._is_on = False
        self.reader = reader

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


class EnvoyStorageReservedSocEntity(EnvoyNumberEntity):
    @property
    def native_value(self) -> float:
        """Return the status of the requested attribute."""
        return int(self.coordinator.data.get("storage_reserved_soc"))

    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        await self.reader.set_storage("reserved_soc", value)
        await self.coordinator.async_request_refresh()
