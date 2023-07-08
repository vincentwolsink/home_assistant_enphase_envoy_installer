"""The Enphase Envoy integration."""
from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import timedelta
import logging
import time

import async_timeout
from .envoy_reader import EnvoyReader, StreamData
import httpx
from numpy import isin

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import HomeAssistant, callback, CoreState, Event
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.storage import Store
from homeassistant.util import Throttle


from .const import (
    COORDINATOR,
    DOMAIN,
    NAME,
    PLATFORMS,
    BINARY_SENSORS,
    SENSORS,
    PHASE_SENSORS,
    CONF_SERIAL,
    READER,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_REALTIME_UPDATE_THROTTLE,
    LIVE_UPDATEABLE_ENTITIES,
    DISABLE_INSTALLER_ACCOUNT_USE,
)

STORAGE_KEY = "envoy"
STORAGE_VERSION = 1

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Enphase Envoy from a config entry."""

    task = None
    config = entry.data
    options = entry.options
    name = config[CONF_NAME]

    # Setup persistent storage, to save tokens between home assistant restarts
    store = Store(hass, STORAGE_VERSION, ".".join([STORAGE_KEY, entry.entry_id]))

    envoy_reader = EnvoyReader(
        config[CONF_HOST],
        enlighten_user=config[CONF_USERNAME],
        enlighten_pass=config[CONF_PASSWORD],
        inverters=True,
        enlighten_serial_num=config[CONF_SERIAL],
        store=store,
        disable_negative_production=options.get("disable_negative_production", False),
        disable_installer_account_use=options.get(DISABLE_INSTALLER_ACCOUNT_USE,config[DISABLE_INSTALLER_ACCOUNT_USE]),
    )
    await envoy_reader._sync_store()

    async def async_update_data():
        """Fetch data from API endpoint."""
        data = {}
        async with async_timeout.timeout(30):
            try:
                await envoy_reader.getData()
            except httpx.HTTPStatusError as err:
                raise ConfigEntryAuthFailed from err
            except httpx.HTTPError as err:
                raise UpdateFailed(f"Error communicating with API: {err}") from err

            for description in BINARY_SENSORS:
                if description.key == "relays":
                    data[description.key] = await envoy_reader.relay_status()

                elif description.key == "firmware":
                    envoy_info = await envoy_reader.envoy_info()
                    data[description.key] = envoy_info.get("update_status", None)

            for description in SENSORS:
                if description.key == "inverters":
                    data[
                        "inverters_production"
                    ] = await envoy_reader.inverters_production()
                    data["inverters_status"] = await envoy_reader.inverters_status()

                elif description.key.startswith("inverters_"):
                    continue

                elif description.key == "batteries":
                    battery_data = await envoy_reader.battery_storage()
                    if isinstance(battery_data, list) and len(battery_data) > 0:
                        battery_dict = {}
                        for item in battery_data:
                            battery_dict[item["serial_num"]] = item

                        data[description.key] = battery_dict

                elif description.key in [
                    "current_battery_capacity",
                    "total_battery_percentage",
                ]:
                    continue

                else:
                    data[description.key] = await getattr(
                        envoy_reader, description.key
                    )()

            for description in PHASE_SENSORS:
                if description.key.startswith("production_"):
                    if envoy_reader.is_receiving_realtime_data:
                        # do not update, use current value
                        data[description.key] = coordinator.data[description.key]
                    else:
                        data[description.key] = await envoy_reader.production_phase(
                            description.key
                        )
                elif description.key.startswith("consumption_"):
                    if envoy_reader.is_receiving_realtime_data:
                        # do not update, use current value
                        data[description.key] = coordinator.data[description.key]
                    else:
                        data[description.key] = await envoy_reader.consumption_phase(
                            description.key
                        )
                elif description.key.startswith("daily_production_"):
                    data[description.key] = await envoy_reader.daily_production_phase(
                        description.key
                    )
                elif description.key.startswith("daily_consumption_"):
                    data[description.key] = await envoy_reader.daily_consumption_phase(
                        description.key
                    )
                elif description.key.startswith("lifetime_production_"):
                    data[
                        description.key
                    ] = await envoy_reader.lifetime_production_phase(description.key)
                elif description.key.startswith("lifetime_consumption_"):
                    data[
                        description.key
                    ] = await envoy_reader.lifetime_consumption_phase(description.key)
                elif description.key.startswith("voltage_"):
                    if envoy_reader.is_receiving_realtime_data:
                        # do not update, use current value
                        data[description.key] = coordinator.data[description.key]
                    else:
                        data[description.key] = await envoy_reader.voltage_phase(
                            description.key
                        )

            data["grid_status"] = await envoy_reader.grid_status()
            data["production_power"] = await envoy_reader.production_power()
            data["envoy_info"] = await envoy_reader.envoy_info()
            data["inverters_info"] = await envoy_reader.inverters_info()
            data["relay_info"] = await envoy_reader.relay_info()

            _LOGGER.debug("Retrieved data from API: %s", data)

            await envoy_reader._sync_store()
            return data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"envoy {name}",
        update_method=async_update_data,
        update_interval=timedelta(
            seconds=options.get("time_between_update", DEFAULT_SCAN_INTERVAL)
        ),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        envoy_reader.get_inverters = False
        await coordinator.async_config_entry_first_refresh()

    if not entry.unique_id:
        try:
            serial = await envoy_reader.get_full_serial_number()
        except httpx.HTTPError:
            pass
        else:
            hass.config_entries.async_update_entry(entry, unique_id=serial)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        COORDINATOR: coordinator,
        NAME: name,
        READER: envoy_reader,
    }
    live_entities = hass.data[DOMAIN][entry.entry_id].setdefault(
        LIVE_UPDATEABLE_ENTITIES, {}
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Finally, start measuring production counters
    time_between_realtime_updates = timedelta(
        seconds=options.get(
            "realtime_update_throttle", DEFAULT_REALTIME_UPDATE_THROTTLE
        ),
    )

    @Throttle(time_between_realtime_updates)
    def update_production_meters(streamdata: StreamData):
        new_data = {}
        for phase in ["l1", "l2", "l3"]:
            production_watts = envoy_reader.process_production_value(
                streamdata.production[phase].watts
            )
            new_data.update(
                {
                    "production_" + phase: production_watts,
                    "voltage_" + phase: streamdata.production[phase].volt,
                    "consumption_" + phase: streamdata.consumption[phase].watts,
                }
            )

        for key, value in new_data.items():
            if live_entities.get(key, False) and coordinator.data.get(key) != value:
                # Update the value in the coordinator
                coordinator.data[key] = value

                # Let hass know the data is updated
                live_entities[key].async_write_ha_state()

    async def read_realtime_updates() -> None:
        while (
            hass.state == CoreState.not_running
            or hass.is_running
            and options.get("enable_realtime_updates", False)
        ):
            result = await envoy_reader.stream_reader(
                meter_callback=update_production_meters
            )
            if result == False:
                # If result is False, then we are done reconnecting
                _LOGGER.warning(
                    "Reading /stream/meter failed, stopping realtime updates"
                )
                return

            _LOGGER.warning("Re-connecting /stream/meter")
            # throttle reconnect attempts
            await asyncio.sleep(30)

    if options.get("enable_realtime_updates", False):
        # Setup a home assistant task (that will never die...)
        _LOGGER.debug("Starting loop for /stream/meter")
        task = asyncio.create_task(read_realtime_updates())

    @callback
    async def _async_stop(_: Event) -> None:
        _LOGGER.debug("Stopping loop for /stream/meter")
        task.cancel()

    # Make sure task is cancelled on shutdown (or tests complete)
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )

    # Save the task to be able to cancel it when unloading
    hass.data[DOMAIN][entry.entry_id]["realtime_loop"] = task
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    if task := hass.data[DOMAIN][entry.entry_id].get("realtime_loop", False):
        _LOGGER.debug("Stopping loop for /stream/meter")
        task.cancel()

        with suppress(asyncio.CancelledError):
            await task

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
