from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.select import SelectEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import COORDINATOR, DOMAIN, NAME, READER, STORAGE_MODES, STORAGE_MODE_SELECT


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
        and coordinator.data.get("storage_mode") is not None
    ):
        entities.append(
            EnvoyStorageModeSelectEntity(
                STORAGE_MODE_SELECT,
                STORAGE_MODE_SELECT.name,
                name,
                config_entry.unique_id,
                None,
                coordinator,
                reader,
            )
        )
    async_add_entities(entities)


class EnvoySelectEntity(CoordinatorEntity, SelectEntity):
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


class EnvoyStorageModeSelectEntity(EnvoySelectEntity):
    @property
    def current_option(self) -> str:
        """Return the status of the requested attribute."""
        return self.coordinator.data.get("storage_mode")

    @property
    def options(self) -> list:
        return STORAGE_MODES

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.reader.set_storage("mode", option)
        await self.coordinator.async_request_refresh()
