from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    COORDINATOR,
    DOMAIN,
    NAME,
    READER,
    SWITCHES,
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
    for switch_description in SWITCHES:
        if switch_description.key.startswith("storage_"):
            if (
                coordinator.data.get("batteries")
                and coordinator.data.get(switch_description.key) is not None
            ):
                entity_name = f"{name} {switch_description.name}"
                entities.append(
                    EnvoyStorageSwitchEntity(
                        switch_description,
                        entity_name,
                        name,
                        config_entry.unique_id,
                        None,
                        coordinator,
                        reader,
                    )
                )
        else:
            if coordinator.data.get(switch_description.key) is not None:
                entity_name = f"{name} {switch_description.name}"
                entities.append(
                    EnvoySwitchEntity(
                        switch_description,
                        entity_name,
                        name,
                        config_entry.unique_id,
                        None,
                        coordinator,
                        reader,
                    )
                )
    async_add_entities(entities)


class EnvoySwitchEntity(CoordinatorEntity, SwitchEntity):
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

    @property
    def is_on(self) -> bool:
        """Return the status of the requested attribute."""
        return self.coordinator.data.get(self.entity_description.key)

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        set_func = getattr(self.reader, f"set_{self.entity_description.key}")
        await set_func(True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        set_func = getattr(self.reader, f"set_{self.entity_description.key}")
        await set_func(False)
        await self.coordinator.async_request_refresh()


class EnvoyStorageSwitchEntity(EnvoySwitchEntity):
    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        await self.reader.set_storage(self.entity_description.key[8:], True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        await self.reader.set_storage(self.entity_description.key[8:], False)
        await self.coordinator.async_request_refresh()
