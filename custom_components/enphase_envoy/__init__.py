"""The Enphase Envoy integration."""

from __future__ import annotations

import asyncio
import copy
import logging
from datetime import timedelta

import async_timeout
import httpx
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_USERNAME,
    EVENT_HOMEASSISTANT_STOP,
)
from homeassistant.core import (
    CoreState,
    Event,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import Throttle

from .const import (
    CONF_SERIAL,
    CONF_TOKEN_SOURCE,
    COORDINATOR,
    DEFAULT_GETDATA_TIMEOUT,
    DEFAULT_REALTIME_UPDATE_THROTTLE,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TOKEN_REFRESH_BUFFER,
    DOMAIN,
    LIVE_UPDATEABLE_ENTITIES,
    NAME,
    PLATFORMS,
    READER,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .envoy_reader import EnlightenError, EnvoyReader, StreamData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Enphase Envoy from a config entry."""

    task: asyncio.Future | None = None
    config = entry.data
    options = entry.options
    name = config[CONF_NAME]

    # Setup persistent storage, to save tokens between home assistant restarts
    store = Store(hass, STORAGE_VERSION, f"{STORAGE_KEY}.{entry.entry_id}")

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
        token_source=config.get(CONF_TOKEN_SOURCE),
        token_refresh_buffer_seconds=DEFAULT_TOKEN_REFRESH_BUFFER,
    )
    await envoy_reader._sync_store(load=True)

    # Keep the Enphase token fresh in the background, so a slow or failing
    # cloud refresh never blocks or fails the data polling cycle.
    token_refresh_task = asyncio.create_task(envoy_reader.run_token_refresh_loop())

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
            except (httpx.HTTPError, EnlightenError) as err:
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
            export_limit=call.data.get("export_limit", True),
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
        total_production = 0
        total_consumption = 0
        total_net_consumption = 0

        # Only use the meter sections for CT types that are actually
        # installed; the Envoy omits the other sections from /stream/meter.
        production_phases = (
            streamdata.production if envoy_reader.production_ct_enabled else {}
        )
        consumption_phases = (
            streamdata.consumption if envoy_reader.consumption_ct_enabled else {}
        )
        net_phases = (
            streamdata.net_consumption if envoy_reader.consumption_ct_enabled else {}
        )
        # Phase electrical values (voltage, frequency, ...) come from the
        # production meter when present, otherwise from the consumption meter.
        electrical_source = production_phases or consumption_phases

        for phase in ["l1", "l2", "l3"]:
            if phase in production_phases:
                production_watts = envoy_reader.process_production_value(
                    production_phases[phase].watts
                )
                total_production += production_watts
                new_data["production_" + phase] = production_watts

            if phase in consumption_phases:
                consumption_watts = consumption_phases[phase].watts
                total_consumption += consumption_watts
                new_data["consumption_" + phase] = consumption_watts

            if phase in net_phases:
                net_consumption_watts = net_phases[phase].watts
                total_net_consumption += net_consumption_watts
                new_data["net_consumption_" + phase] = net_consumption_watts

            if phase in electrical_source:
                phase_data = electrical_source[phase]
                new_data.update(
                    {
                        "voltage_" + phase: phase_data.volt,
                        "ampere_" + phase: phase_data.amps,
                        "apparent_power_" + phase: phase_data.volt_ampere,
                        "power_factor" + phase: phase_data.pf,
                        "reactive_power_" + phase: phase_data.var,
                        "frequency_" + phase: phase_data.hz,
                    }
                )

        if production_phases:
            new_data["production"] = total_production
        if consumption_phases:
            new_data["consumption"] = total_consumption
        if net_phases:
            new_data["net_consumption"] = total_net_consumption

        for key, value in new_data.items():
            if live_entities.get(key, False) and coordinator.data.get(key) != value:
                # Update the value in the coordinator
                coordinator.data[key] = value

                # Let hass know the data is updated
                if live_entities[key].hass:
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
            if not result:
                # If result is False, then we are done reconnecting
                _LOGGER.warning(
                    "Reading /stream/meter failed, stopping realtime updates"
                )
                return

            _LOGGER.debug("Re-connecting /stream/meter")
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

        if token_refresh_task and not token_refresh_task.done():
            _LOGGER.debug("Stopping token refresh loop")
            await _cancel_realtime_task(token_refresh_task)
            hass.data[DOMAIN][entry.entry_id]["token_refresh_loop"] = False

    # Make sure task is cancelled on shutdown (or tests complete)
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    )

    # Save the task to be able to cancel it when unloading
    hass.data[DOMAIN][entry.entry_id]["realtime_loop"] = task
    hass.data[DOMAIN][entry.entry_id]["token_refresh_loop"] = token_refresh_task
    return True


async def _cancel_realtime_task(task: asyncio.Future | None) -> None:
    if not task:
        _LOGGER.debug("No task to cancel")
        return

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception:
        _LOGGER.exception(
            "While waiting for task to be cancelled, an exception occured"
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    if task := hass.data[DOMAIN][entry.entry_id].get("realtime_loop"):
        _LOGGER.debug("Stopping loop for /stream/meter")
        await _cancel_realtime_task(task)

        hass.data[DOMAIN][entry.entry_id]["realtime_loop"] = False

    if task := hass.data[DOMAIN][entry.entry_id].get("token_refresh_loop"):
        _LOGGER.debug("Stopping token refresh loop")
        await _cancel_realtime_task(task)

        hass.data[DOMAIN][entry.entry_id]["token_refresh_loop"] = False

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
