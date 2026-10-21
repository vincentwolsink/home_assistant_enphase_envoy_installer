from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    COORDINATOR,
    DOMAIN,
    INVERTER_SWITCHES,
    NAME,
    READER,
    SWITCHES,
    get_model_name,
)
from .helpers import via_device_kw


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
    if reader.supports_dpel:
        entities.append(
            EnvoyDpelSwitchEntity(
                name,
                name,
                config_entry.unique_id,
                None,
                coordinator,
                reader,
            )
        )

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

    # Every microinverter can be forced on/off individually. The power
    # state is only known when the installer token is used.
    for switch_description in INVERTER_SWITCHES:
        for serial_number in coordinator.data.get("inverter_power") or {}:
            device_name = f"Inverter {serial_number}"
            entity_name = f"{device_name} {switch_description.name}"
            entities.append(
                EnvoyInverterSwitchEntity(
                    switch_description,
                    entity_name,
                    device_name,
                    serial_number,
                    None,
                    coordinator,
                    reader,
                    config_entry,
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


class EnvoyInverterSwitchEntity(EnvoySwitchEntity):
    """Switch to force the production of a single microinverter on or off."""

    def __init__(
        self,
        description,
        name,
        device_name,
        device_serial_number,
        serial_number,
        coordinator,
        reader,
        config_entry,
    ):
        super().__init__(
            description,
            name,
            device_name,
            device_serial_number,
            serial_number,
            coordinator,
            reader,
        )
        self._config_entry = config_entry

    @property
    def _inverter(self):
        """Return the known power state of this microinverter."""
        return (self.coordinator.data.get("inverter_power") or {}).get(
            self._device_serial_number
        )

    @property
    def is_on(self) -> bool:
        """Return the status of the requested attribute."""
        inverter = self._inverter
        if inverter is None:
            return None
        return inverter.get("power_on")

    @property
    def available(self) -> bool:
        """The power state is only known with an installer token."""
        return super().available and self._inverter is not None

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return the device_info of the device."""
        if not self._device_serial_number:
            return None

        device_info_kw = via_device_kw(self.hass, self._config_entry)

        inverter_info = self.coordinator.data.get("inverter_info") or {}
        if inverter_info.get(self._device_serial_number):
            device_info_kw["sw_version"] = inverter_info.get(
                self._device_serial_number
            ).get("img_pnum_running")
            device_info_kw["hw_version"] = inverter_info.get(
                self._device_serial_number
            ).get("part_num")

        model_name = get_model_name("Inverter", device_info_kw.get("hw_version"))

        return DeviceInfo(
            identifiers={(DOMAIN, str(self._device_serial_number))},
            manufacturer="Enphase",
            model=model_name,
            name=self._device_name,
            serial_number=str(self._device_serial_number),
            **device_info_kw,
        )

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        await self.reader.set_inverter_power(self._device_serial_number, True)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        await self.reader.set_inverter_power(self._device_serial_number, False)
        await self.coordinator.async_request_refresh()


class EnvoyDpelSwitchEntity(CoordinatorEntity, SwitchEntity):
    def __init__(
        self,
        name,
        device_name,
        device_serial_number,
        serial_number,
        coordinator,
        reader,
    ):
        self.entity_description = SwitchEntityDescription(
            key="dpel_enabled",
            name="DPEL",
            icon="mdi:transmission-tower-import",
            device_class=SwitchDeviceClass.SWITCH,
        )
        self._name = name
        self._serial_number = serial_number
        self._device_name = device_name
        self._device_serial_number = device_serial_number
        CoordinatorEntity.__init__(self, coordinator)
        self.reader = reader

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._name} {self.entity_description.name}"

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
        return self.coordinator.data.get("dpel_enabled")

    @property
    def available(self) -> bool:
        """The DPEL endpoint is only readable with an installer token."""
        return super().available and self.reader.endpoint_dpel is not None

    async def async_turn_on(self, **kwargs):
        """Turn the entity on."""
        await self.reader.enable_dpel(
            watt=self.coordinator.data.get("dpel_limit", 0) or 0,
            export_limit=self.coordinator.data.get("dpel_mode") == "Export",
        )
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs):
        """Turn the entity off."""
        await self.reader.disable_dpel()
        await self.coordinator.async_request_refresh()
