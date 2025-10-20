"""The Enphase Envoy integration."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import timedelta
import logging
import time
from typing import Optional
import copy

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
from homeassistant.core import (
    HomeAssistant,
    callback,
    CoreState,
    Event,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
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
    DEFAULT_GETDATA_TIMEOUT,
)

STORAGE_KEY = "envoy"
STORAGE_VERSION = 1

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Enphase Envoy from a config entry."""

    task: Optional[asyncio.Future] = None
    config = entry.data
    options = entry.options
    name = config[CONF_NAME]

    # Setup persistent storage, to save tokens between home assistant restarts
    store = Store(hass, STORAGE_VERSION, ".".join([STORAGE_KEY, entry.entry_id]))

    disabled_endpoints = options.get("disabled_endpoints", [])
    if (
        not options.get("enable_pcu_comm_check")
        and "endpoint_pcu_comm_check" not in disabled_endpoints
    ):
        disabled_endpoints = copy.copy(disabled_endpoints)
        disabled_endpoints.append("endpoint_pcu_comm_check")

    envoy_reader = EnvoyReader(
        config[CONF_HOST],
        enlighten_user=config[CONF_USERNAME],
        enlighten_pass=config[CONF_PASSWORD],
        inverters=True,
        enlighten_serial_num=config[CONF_SERIAL],
        store=store,
        disable_negative_production=options.get("disable_negative_production", False),
        disabled_endpoints=disabled_endpoints,
        lifetime_production_correction=options.get("lifetime_production_correction", 0),
        device_data_endpoint=(
            "endpoint_devstatus"
            if options.get("devstatus_device_data", False)
            else "endpoint_device_data"
        ),
    )
    await envoy_reader._sync_store(load=True)

    async def async_update_data():
        """Fetch data from API endpoint."""
        data = {}
        async with async_timeout.timeout(
            options.get("getdata_timeout", DEFAULT_GETDATA_TIMEOUT)
        ):
            try:
                await envoy_reader.get_data()
            except httpx.HTTPStatusError as err:
                raise ConfigEntryAuthFailed from err
            except httpx.HTTPError as err:
                raise UpdateFailed(f"Error communicating with API: {err}") from err

            # The envoy_reader.all_values will adjust production values, based on option key
            data = envoy_reader.all_values

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

    async def async_enable_dpel(call: ServiceCall):
        await envoy_reader.enable_dpel(
            watt=call.data.get("watt"), 
            slew=call.data.get("slew_rate", 50), 
            export_limit=call.data.get("export_limit", True)
        )
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "enable_dpel", async_enable_dpel)

    async def async_disable_dpel(call: ServiceCall):
        await envoy_reader.disable_dpel()
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, "disable_dpel", async_disable_dpel)

    async def get_grid_profiles(call: ServiceCall) -> ServiceResponse:
        return {
            "selected_profile": coordinator.data.get("grid_profile"),
            "available_profiles": [
                k["profile_id"] for k in coordinator.data.get("grid_profiles_available")
            ],
        }

    hass.services.async_register(
        DOMAIN,
        "get_grid_profiles",
        get_grid_profiles,
        supports_response=SupportsResponse.ONLY,
    )

    async def set_grid_profile(call: ServiceCall):
        await envoy_reader.set_grid_profile(call.data["profile"])
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "set_grid_profile",
        set_grid_profile,
    )

    async def upload_grid_profile(call: ServiceCall):
        await envoy_reader.upload_grid_profile(call.data["file"])
        await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        "upload_grid_profile",
        upload_grid_profile,
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
                    "ampere_" + phase: streamdata.production[phase].amps,
                    "apparent_power_" + phase: streamdata.production[phase].volt_ampere,
                    "power_factor" + phase: streamdata.production[phase].pf,
                    "reactive_power_" + phase: streamdata.production[phase].var,
                    "frequency_" + phase: streamdata.production[phase].hz,
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
        await _cancel_realtime_task(task)

        hass.data[DOMAIN][entry.entry_id]["realtime_loop"] = False

    # Make sure task is cancelled on shutdown (or tests complete)
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )

    # Save the task to be able to cancel it when unloading
    hass.data[DOMAIN][entry.entry_id]["realtime_loop"] = task
    return True


async def _cancel_realtime_task(task: Optional[asyncio.Future]) -> None:
    if not task:
        _LOGGER.debug("No task to cancel")
        return

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as e:
        _LOGGER.exception(
            f"While waiting for task to be cancelled, this execption occured: {e}"
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    if task := hass.data[DOMAIN][entry.entry_id].get("realtime_loop"):
        _LOGGER.debug("Stopping loop for /stream/meter")
        await _cancel_realtime_task(task)

        hass.data[DOMAIN][entry.entry_id]["realtime_loop"] = False

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
