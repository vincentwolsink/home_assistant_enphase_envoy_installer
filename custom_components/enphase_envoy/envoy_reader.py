"""Module to read production and consumption values from an Enphase Envoy on the local network."""
import argparse
import asyncio
import datetime
import time
import logging
import jwt
import xmltodict
import httpx
import ipaddress
import json
import os

from jsonpath import jsonpath
from functools import partial

import hashlib
import base64
import random
import string
from urllib import parse

from json.decoder import JSONDecodeError

ENDPOINT_URL_INVENTORY = "https://{}/inventory.json"
ENDPOINT_URL_PRODUCTION_JSON = "https://{}/production.json?details=1"
ENDPOINT_URL_PRODUCTION_V1 = "https://{}/api/v1/production"
ENDPOINT_URL_PRODUCTION_INVERTERS = "https://{}/api/v1/production/inverters"
ENDPOINT_URL_CHECK_JWT = "https://{}/auth/check_jwt"
ENDPOINT_URL_ENSEMBLE_INVENTORY = "https://{}/ivp/ensemble/inventory"
ENDPOINT_URL_HOME_JSON = "https://{}/home.json"
ENDPOINT_URL_DEVSTATUS = "https://{}/ivp/peb/devstatus"
ENDPOINT_URL_PRODUCTION_POWER = "https://{}/ivp/mod/603980032/mode/power"
ENDPOINT_URL_INFO_XML = "https://{}/info.xml"
ENDPOINT_URL_STREAM = "https://{}/stream/meter"
ENDPOINT_URL_PDM_ENERGY = "https://{}/ivp/pdm/energy"

ENVOY_MODEL_S = "PC"
ENVOY_MODEL_C = "P"

# paths for the enlighten installer token
ENLIGHTEN_AUTH_URL = "https://enlighten.enphaseenergy.com/login/login.json"
ENLIGHTEN_TOKEN_URL = "https://entrez.enphaseenergy.com/tokens"

# paths used for fetching enlighten token through envoy
ENLIGHTEN_LOGIN_URL = "https://entrez.enphaseenergy.com/login"
ENDPOINT_URL_GET_JWT = "https://{}/auth/get_jwt"

TEST_DATA_FOLDER = os.path.join(os.path.dirname(__file__), "test_data")

_LOGGER = logging.getLogger(__name__)


def random_content(length):
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for i in range(length))


def generate_challenge(code):
    sha_code = hashlib.sha256()
    sha_code.update(code.encode("utf-8"))

    return (
        base64.b64encode(sha_code.digest())
        .decode("utf-8")
        .replace("+", "-")  # + will be -
        .replace("/", "_")  # / will be _
        .replace("=", "")  # remove = chars
    )


def has_production_and_consumption(json):
    """Check if json has keys for both production and consumption."""
    return "production" in json and "consumption" in json


def has_metering_setup(json):
    """Check if Active Count of Production CTs (eim) installed is greater than one."""
    return json["production"][1]["activeCount"] > 0


def parse_devstatus(data):
    def convert_dev(dev):
        def iter():
            for key, value in dev.items():
                if key == "reportDate":
                    yield "report_date", time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(value)
                    )
                elif key == "dcVoltageINmV":
                    yield "dc_voltage", int(value) / 1000
                elif key == "dcCurrentINmA":
                    yield "dc_current", int(value) / 1000
                elif key == "acVoltageINmV":
                    yield "ac_voltage", int(value) / 1000
                elif key == "acPowerINmW":
                    yield "ac_power", int(value) / 1000
                else:
                    yield key, value

        return dict(iter())

    new_data = {}
    for key, val in data.items():
        if val.get("fields", None) == None or val.get("values", None) == None:
            new_data[key] = val
            continue

        new_data[key] = [
            convert_dev(dict(zip(val["fields"], entry))) for entry in val["values"]
        ]
    return new_data


def load_test_data(full_fname):
    """Load test data from test_data directory"""
    _LOGGER.debug("Reading test data from %s", full_fname)
    with open(full_fname, "r") as fh:
        if full_fname.endswith(".json"):
            data = json.load(fh)
            if "endpoint_devstatus" in full_fname:
                data = parse_devstatus(data)
            return data

        elif full_fname.endswith(".xml"):
            return xmltodict.parse(fh.read())

        return fh.read()


class SwitchToHTTPS(Exception):
    pass


class StreamData:
    class PhaseData:
        def __init__(self, phase_data):
            self.watts = phase_data["p"]  # wNow, W
            self.amps = phase_data["i"]  # rmsCurrent, A
            self.volt_ampere = phase_data["s"]  # apparent_power, VA
            self.volt = phase_data["v"]  # rmsVoltage, V
            self.pf = phase_data["pf"]  # pwrFactor, PF
            self.hz = phase_data["f"]  # Frequency, Hz

            # no clue what the q key is (the webui also has no reference to it.)
            # self.power_?? = phase_data["q"]

        def __str__(self):
            return "<Phase %s watts, %s volt, %s amps, %s va, %s hz, %s pf />" % (
                self.watts,
                self.volt,
                self.amps,
                self.volt_ampere,
                self.hz,
                self.pf,
            )

    def __init__(self, data):
        self.production = {}
        self.consumption = {}
        self.net_consumption = {}

        phase_mapping = {"ph-a": "l1", "ph-b": "l2", "ph-c": "l3"}
        for data_key, attr in {
            "production": "production",
            "total-consumption": "consumption",
            "net-consumption": "net_consumption",
        }.items():
            for phase_key, phase in phase_mapping.items():
                if not data.get(data_key, {}).get(phase_key, False):
                    continue
                getattr(self, attr)[phase] = self.PhaseData(data[data_key][phase_key])

    def __str__(self):
        return "<StreamData production=%s, consumption=%s, net_consumption=%s />" % (
            dict([[k, str(v)] for k, v in self.production.items()]),
            dict([[k, str(v)] for k, v in self.consumption.items()]),
            dict([[k, str(v)] for k, v in self.net_consumption.items()]),
        )


def envoy_property(*a, **kw):
    endpoint = kw.pop("required_endpoint", None)

    def prop(f):
        EnvoyData._envoy_properties[f.__name__] = endpoint
        return property(f)

    if endpoint != None or len(a) == 0:
        return prop
    return prop(*a)


def path_by_token(owner, installer=None):
    def path(cls):
        if cls.reader.token_type == "installer" and installer:
            return installer
        return owner

    return property(path)


class EnvoyData(object):
    """Functions in this class will provide getters and setters for data to be provided"""

    _envoy_properties = {}

    def __new__(cls, *a, **kw):
        cls._attributes = []
        for attr in dir(cls):
            if attr.endswith("_value"):
                cls._attributes.append(attr[:-6])

            elif isinstance(getattr(cls, attr), property):
                if attr in cls._envoy_properties:
                    cls._attributes.append(attr)

        return object.__new__(cls)

    def __init__(self, reader):
        self.reader = reader
        self.data = {}
        self.initial_update_finished = False
        self._required_endpoints = None
        super(object, self).__init__()

    def _read_test_data(self, test_data_folder=None):
        path = TEST_DATA_FOLDER
        if test_data_folder:
            path = os.path.join(TEST_DATA_FOLDER, test_data_folder)

        for path, _, filenames in os.walk(path):
            for filename in filenames:
                datakey = filename.split(".", 1)[0]
                self.data.update(
                    {
                        datakey: load_test_data(os.path.join(path, filename)),
                    }
                )

    def set_endpoint_data(self, endpoint, response):
        """Called by EnvoyReader.update_endpoints when a response is successfull"""
        if response.status_code > 400:
            # It is a server error, do not store endpoint_data
            return

        content_type = response.headers.get("content-type", "application/json")
        if endpoint == "endpoint_devstatus":
            # Do extra parsing, to zip the fields and values and make it a proper dict
            self.data[endpoint] = parse_devstatus(response.json())
        elif content_type == "application/json":
            self.data[endpoint] = response.json()
        elif content_type in ("text/xml", "application/xml"):
            self.data[endpoint] = xmltodict.parse(response.text)
        else:
            self.data[endpoint] = response.text

    @property
    def required_endpoints(self):
        """Method that will return all endpoints which are defined in the _value parameters."""
        if self._required_endpoints != None:  # return cached value
            return self._required_endpoints

        endpoints = set()

        # Loop through all local attributes, and return unique first required jsonpath attribute.
        for attr in dir(self):
            if attr.endswith("_value") and isinstance(
                (path := getattr(self, attr)), (str)
            ):
                if self.initial_update_finished:
                    # Check if the path resolves, if not, do not include endpoint.
                    if self._resolve_path(path) is None:
                        # If the resolved path is None, we skip this path for the endpoints
                        continue

                endpoints.add(path.split(".", 1)[0])
                continue  # discovered, so continue

            if attr in self._envoy_properties and isinstance(
                self._envoy_properties[attr], str
            ):
                value = getattr(self, attr)
                if self.initial_update_finished and value in (None, [], {}):
                    # When the value is None or empty list or dict,
                    # then the endpoint is useless for this token,
                    # so do not require it.
                    continue

                endpoints.add(self._envoy_properties[attr])

        if self.initial_update_finished:
            # Save the list in memory, as we should not evaluate this list again.
            # If the list needs re-evaluation, then reload the plugin.
            self._required_endpoints = endpoints

        return endpoints

    @property
    def all_values(self):
        """A special property attribute, that will return all dynamic fields."""
        result = {}
        for attr in self._attributes:
            result[attr] = self.get(attr)

        return result

    def _resolve_path(self, path, default=None):
        _LOGGER.debug("Resolving jsonpath %s", path)

        result = jsonpath(self.data, path)
        if result == False:
            _LOGGER.debug("the configured path %s did not return anything!", path)
            return default

        if len(result) == 1 and isinstance(result, list):
            result = result[0]

        return result

    def _path_to_dict(self, paths, keyfield):
        if not isinstance(paths, list):
            paths = [paths]

        new_dict = {}
        for path in paths:
            data = self._resolve_path(path, default=[])
            if not isinstance(data, list):
                data = [data]
            for d in data:
                key = d.get(keyfield)
                new_dict.setdefault(key, d).update(**d)

        return new_dict

    def get(self, name):
        result = None
        if (attr := f"{name}_value") in dir(self):
            path = getattr(self, attr)
            result = self._resolve_path(path)
        elif name in self._envoy_properties:
            result = getattr(self, name)
        else:
            _LOGGER.debug("Attribute %s unknown", name)

        _LOGGER.debug(f"EnvoyData.get({name}) -> {result}")
        return result


class EnvoyStandard(EnvoyData):
    """This entity should only hold jsonpath queries on how to fetch the data"""

    envoy_pn_value = "endpoint_info_results.envoy_info.device.pn"
    has_integrated_meter_value = (
        "endpoint_info_results.envoy_info.device.imeter"  # true/false value
    )
    envoy_software_value = "endpoint_info_results.envoy_info.device.software"
    envoy_software_build_epoch_value = "endpoint_home_json_results.software_build_epoch"
    envoy_update_status_value = "endpoint_home_json_results.update_status"
    serial_number_value = "endpoint_info_results.envoy_info.device.sn"

    @envoy_property
    def envoy_info(self):
        return {
            "pn": self.get("envoy_pn"),
            "software": self.get("envoy_software"),
            "software_build_epoch": self.get("envoy_software_build_epoch"),
            "update_status": self.get("envoy_update_status_value"),
        }

    production_value = path_by_token(
        owner="endpoint_production_v1_results.wattsNow",
        installer="endpoint_pdm_energy.production.pcu.wattsNow",
    )
    daily_production_value = path_by_token(
        owner="endpoint_production_v1_results.wattHoursToday",
        installer="endpoint_pdm_energy.production.pcu.wattHoursToday",
    )
    lifetime_production_value = path_by_token(
        owner="endpoint_production_v1_results.wattHoursLifetime",
        installer="endpoint_pdm_energy.production.pcu.wattHoursLifetime",
    )

    @envoy_property(required_endpoint="endpoint_production_power")
    def production_power(self):
        """Return production power status reported by Envoy"""
        force_off = self._resolve_path("endpoint_production_power.powerForcedOff")
        if force_off != None:
            return not force_off

    # This is a enpower / battery value, if the value is None it will increase
    # the cache time of the endpoint, as the information is not required
    # to be as up-to-date, since it pretty stale information anyway for
    # non-battery setups.
    # how to prevent from continuesly fetching home.json when no batteries
    @envoy_property(required_endpoint="endpoint_home_json_results")
    def grid_status(self):
        grid_status = self._resolve_path(
            "endpoint_home_json_results.enpower.grid_status"
        )
        if grid_status == None:
            # This is the only property we use that actually should be refreshed often.
            # So if the value is None (e.g. not found),
            # then we ought to cache the result more often.
            self.reader.uri_registry["endpoint_home_json_results"]["cache_time"] = 86400

        return grid_status

    inverters_data_value = path_by_token(
        owner="endpoint_production_inverters.[?(@.devType==1)]",
        installer="endpoint_devstatus.pcu[?(@.devType==1)]",
    )

    @envoy_property
    def inverters_production(self):
        # We will use the endpoint based on the token_type, which is automatically resolved by the inverters_data property
        data = self.get("inverters_data")

        def iter():
            if self.reader.token_type == "installer":
                for item in data:
                    yield item["serialNumber"], {
                        "watt": item["ac_power"],
                        "report_data": item["report_date"],
                    }
            else:
                # endpoint_production_inverters endpoint
                for item in data:
                    yield item["serialNumber"], {
                        "watt": item["lastReportWatts"],
                        "report_data": time.strftime(
                            "%Y-%m-%d %H:%M:%S", time.localtime(item["lastReportDate"])
                        ),
                    }

        return dict(iter())

    @envoy_property(required_endpoint="endpoint_inventory_results")
    def inverters_info(self):
        return self._path_to_dict(
            "endpoint_inventory_results.[?(@.type=='PCU')].devices[?(@.dev_type==1)]",
            "serial_num",
        )

    @envoy_property(required_endpoint="endpoint_inventory_results")
    def relay_info(self):
        return self._path_to_dict(
            "endpoint_inventory_results.[?(@.type=='NSRB')].devices[?(@.dev_type==12)]",
            "serial_num",
        )

    @envoy_property(required_endpoint="endpoint_devstatus")
    def inverters_status(self):
        return self._path_to_dict(
            "endpoint_devstatus.pcu[?(@.devType==1)]",
            "serialNumber",
        )

    @envoy_property(required_endpoint="endpoint_devstatus")
    def relay_status(self):
        status = self._path_to_dict(
            [
                "endpoint_devstatus.pcu[?(@.devType==12)]",
                "endpoint_devstatus.nsrb",
            ],
            "serialNumber",
        )
        if not status:
            # fallback to the information which is available with owner token.
            status = self.relay_info
        return status

    @envoy_property(required_endpoint="endpoint_ensemble_json_results")
    def battery_storage(self):
        """Return battery data from Envoys that support and have batteries installed"""
        storage = self._resolve_path("endpoint_production_json_results.storage[0]", {})
        if storage.get("percentFull", False):
            """For Envoys that support batteries but do not have them installed the
            percentFull will not be available in the JSON results. The API will
            only return battery data if batteries are installed."""

            # Update endpoint requirement to use endpoint_production_json_results
            self._envoy_properties.update(
                battery_storage="endpoint_production_json_results"
            )
            return storage

        # "ENCHARGE" batteries are part of the "ENSEMBLE" api instead
        # Check to see if it's there. Enphase has too much fun with these names
        return self._resolve_path("endpoint_ensemble_json_results[0].devices")


class EnvoyMetered(EnvoyStandard):
    """
    Same as EnvoyStandard, but should also have some voltage and frequency sensors,
    from the wire(s) that power the envoy
    """

    def __new__(cls, *a, **kw):
        # Add phase CT consumption value attributes, as production values
        # are fetched from inverters, but a CT _could_ be installed for consumption
        for attr, path in {
            "consumption": ".wNow",
            "daily_consumption": ".whToday",
            "lifetime_consumption": ".whLifetime",
        }.items():
            ct_path = cls._consumption_ct
            setattr(cls, f"{attr}_value", ct_path + path)

            for i, phase in enumerate(["l1", "l2", "l3"]):
                full_path = f"{ct_path}.lines[{i}]{path}"
                setattr(cls, f"{attr}_{phase}_value", full_path)

        return EnvoyStandard.__new__(cls)

    _production = "endpoint_production_json_results.production[?(@.type=='inverters')]"
    production_value = _production + ".wNow"
    lifetime_production_value = path_by_token(
        owner=_production + ".whLifetime",
        installer="endpoint_pdm_energy.production.pcu.wattHoursLifetime",
    )
    daily_production_value = "endpoint_pdm_energy.production.pcu.wattHoursToday"

    _production_ct = "endpoint_production_json_results.production[?(@.type=='eim' && @.activeCount > 0)]"
    _consumption_ct = "endpoint_production_json_results.consumption[?(@.measurementType == 'total-consumption' && @.activeCount > 0)]"
    voltage_value = _production_ct + ".rmsVoltage"


class EnvoyMeteredWithCT(EnvoyMetered):
    """Adds CT based sensors, like current usage per phase"""

    def __new__(cls, *a, **kw):
        # Add phase CT production value attributes, as this class is
        # chosen when one production CT is enabled.
        for attr, path in {
            "production": ".wNow",
            "daily_production": ".whToday",
            "lifetime_production": ".whLifetime",
            "voltage": ".rmsVoltage",
        }.items():
            ct_path = cls._production_ct
            setattr(cls, f"{attr}_value", ct_path + path)

            # Also create paths for all phases.
            for i, phase in enumerate(["l1", "l2", "l3"]):
                full_path = f"{ct_path}.lines[{i}]{path}"
                setattr(cls, f"{attr}_{phase}_value", full_path)

        return EnvoyMetered.__new__(cls)


def getEnvoyDataClass(envoy_type, production_json):
    if envoy_type == ENVOY_MODEL_C:
        return EnvoyStandard

    # It is a metered Envoy, check the production json if the eim entry has activeCount > 0
    for prod in production_json.get("production", []):
        if prod["type"] == "eim" and prod["activeCount"] > 0:
            return EnvoyMeteredWithCT

    return EnvoyMetered


class EnvoyReader:
    """Instance of EnvoyReader"""

    # P for production data only (ie. Envoy model C, s/w >= R3.9)
    # PC for production and consumption data (ie. Envoy model S)

    def __init__(
        self,
        host,
        inverters=False,
        async_client=None,
        enlighten_user=None,
        enlighten_pass=None,
        commissioned=False,
        enlighten_serial_num=None,
        token_refresh_buffer_seconds=0,
        store=None,
        disable_negative_production=False,
        disable_installer_account_use=False,
    ):
        """Init the EnvoyReader."""
        self.host = host.lower()
        self.get_inverters = inverters
        self.endpoint_type = None
        self.serial_number_last_six = None

        self.url_last_queried = {}
        self.fetch_task = None

        self._async_client = async_client
        self._authorization_header = None
        self._cookies = None
        self.enlighten_user = enlighten_user
        self.enlighten_pass = enlighten_pass
        self.commissioned = commissioned
        self.envoy_token_fetch_attempted = False
        self.enlighten_serial_num = enlighten_serial_num
        self.token_refresh_buffer_seconds = token_refresh_buffer_seconds
        self.token_type = None

        self.data: EnvoyData = EnvoyStandard(self)
        self.required_endpoints = set()  # in case we would need it..

        def url(endpoint, *a, **kw):
            return self.register_url(f"endpoint_{endpoint}", *a, **kw)

        # iurl is for registering endpoints that require a installer token
        iurl = partial(url, installer_required="installer")

        self.uri_registry = {}
        url("production_json_results", ENDPOINT_URL_PRODUCTION_JSON, cache=0)
        url("production_v1_results", ENDPOINT_URL_PRODUCTION_V1, cache=20)
        url("production_inverters", ENDPOINT_URL_PRODUCTION_INVERTERS, cache=20)
        url("ensemble_json_results", ENDPOINT_URL_ENSEMBLE_INVENTORY)
        # cache for home_json will be set based on grid_status availability
        url("home_json_results", ENDPOINT_URL_HOME_JSON)
        iurl("devstatus", ENDPOINT_URL_DEVSTATUS, cache=20)
        iurl("production_power", ENDPOINT_URL_PRODUCTION_POWER, cache=3600)
        url("info_results", ENDPOINT_URL_INFO_XML, cache=86400)
        url("inventory_results", ENDPOINT_URL_INVENTORY, cache=300)
        iurl("pdm_energy", ENDPOINT_URL_PDM_ENERGY)

        # If IPv6 address then enclose host in brackets
        try:
            ipv6 = ipaddress.IPv6Address(self.host)
            self.host = f"[{ipv6}]"
        except ipaddress.AddressValueError:
            pass

        self.disable_negative_production = disable_negative_production
        self.disable_installer_account_use = disable_installer_account_use

        self.is_receiving_realtime_data = False

        self._store = store
        self._store_data = {}
        self._store_update_pending = False

    def __getattr__(self, name):
        """
        Magic attribute function that will return async method to be called from HA
        for dynamically calling production, or consumption or other sensor data.
        """

        async def get_data():
            return self.data.get(name)

        if self.data:
            return get_data

        raise AttributeError(f"Attribute {name} not found")

    def register_url(self, attr, uri, cache=10, installer_required=False):
        self.uri_registry[attr] = {
            "url": uri,
            "cache_time": cache,
            "last_fetch": 0,
            "installer_required": installer_required,
        }
        setattr(self, attr, None)
        return self.uri_registry[attr]

    def _clear_endpoint_cache(self, attr):
        if not attr in self.uri_registry[attr]:
            return

        # Setting last_fetch to 0 ensures it will be fetched upon next run
        self.uri_registry[attr]["last_fetch"] = 0

    @property
    def _token(self):
        return self._store_data.get("token", "")

    @_token.setter
    def _token(self, token_value):
        self._store_data["token"] = token_value
        self._store_update_pending = True

    async def _sync_store(self, load=False):
        if (self._store and not self._store_data) or load:
            self._store_data = await self._store.async_load() or {}

        if self._store and self._store_update_pending:
            self._store_update_pending = False
            await self._store.async_save(self._store_data)

    @property
    def async_client(self):
        """Return the httpx client."""
        return self._async_client or httpx.AsyncClient(verify=False)

    async def _update_endpoint(self, attr, url, only_on_success=False):
        """Update a property from an endpoint."""
        formatted_url = url.format(self.host)
        response = await self._async_fetch_with_retry(
            formatted_url, follow_redirects=False
        )
        if not only_on_success or response.status_code == 200:
            setattr(self, attr, response)

    async def _async_fetch_with_retry(self, url, **kwargs):
        """Retry 3 times to fetch the url if there is a transport error."""
        received_401 = 0
        for attempt in range(3):
            _LOGGER.debug(
                "HTTP GET Attempt #%s: %s: Header:%s Cookies:%s",
                attempt + 1,
                url,
                self._authorization_header,
                self._cookies,
            )
            try:
                async with self.async_client as client:
                    resp = await client.get(
                        url,
                        headers=self._authorization_header,
                        cookies=self._cookies,
                        timeout=30,
                        **kwargs,
                    )
                    if resp.status_code == 401 and attempt < 2:
                        _LOGGER.debug(
                            "Received 401 from Envoy; refreshing token, attempt %s of 2",
                            attempt + 1,
                        )
                        # Only on the first 401 response, we refresh token cookies,
                        # otherwise we just fetch a new enphase token
                        could_refresh_cookies = (
                            await self._refresh_token_cookies()
                            if received_401 == 0
                            else False
                        )
                        if not could_refresh_cookies:
                            await self._getEnphaseToken()

                        received_401 += 1
                        continue
                    _LOGGER.debug("Fetched from %s: %s: %s", url, resp, resp.text)
                    if resp.status_code == 404:
                        return None
                    return resp
            except httpx.TransportError as e:
                _LOGGER.debug("TransportError: %s", e)
                if attempt == 2:
                    raise e

    async def _async_post(self, url, data=None, **kwargs):
        _LOGGER.debug("HTTP POST Attempt: %s", url)
        _LOGGER.debug("HTTP POST Data: %s", data)
        try:
            async with self.async_client as client:
                resp = await client.post(
                    url,
                    headers=self._authorization_header,
                    cookies=self._cookies,
                    data=data,
                    timeout=30,
                    **kwargs,
                )
                _LOGGER.debug("HTTP POST %s: %s: %s", url, resp, resp.text)
                _LOGGER.debug("HTTP POST Cookie: %s", resp.cookies)
                return resp
        except httpx.TransportError:
            raise

    async def _async_put(self, url, data, **kwargs):
        _LOGGER.debug(
            "HTTP PUT Attempt: %s Header: %s", url, self._authorization_header
        )
        _LOGGER.debug("HTTP PUT Data: %s", data)
        try:
            async with self.async_client as client:
                resp = await client.put(
                    url,
                    headers=self._authorization_header,
                    cookies=self._cookies,
                    json=data,
                    timeout=30,
                    **kwargs,
                )
                _LOGGER.debug("HTTP PUT %s: %s: %s", url, resp, resp.text)
                return resp
        except httpx.TransportError:
            raise

    async def _fetch_envoy_token_json(self):
        """
        Fetch a token, using the same procedure envoy uses in the webUI

        :returns received access_token
        """
        _LOGGER.debug("Fetching envoy token")
        async with self.async_client as client:
            # Step 1, generate local secret
            code_verifier = random_content(40)

            _LOGGER.debug("Local auth secret: %s", code_verifier)

            # Step 2, call the entrez login with form fields
            # all params are reverse engineered, so prone to changes
            login_data = dict(
                username=self.enlighten_user,
                password=self.enlighten_pass,
                codeChallenge=generate_challenge(code_verifier),
                redirectUri=f"https://{self.host}/auth/callback",
                client="envoy-ui",
                clientId="envoy-ui-client",
                authFlow="oauth",
                serialNum=self.enlighten_serial_num,
                granttype="authorize",
                state="",
                invalidSerialNum="",
            )
            _LOGGER.debug(
                "Doing authorize at entrez, with codeChallenge: %s",
                login_data["codeChallenge"],
            )
            resp = await client.post(ENLIGHTEN_LOGIN_URL, data=login_data)

            if resp.status_code >= 400:
                raise Exception("Could not Login via Enlighten")

            # we should expect a 302 redirect
            if resp.status_code != 302:
                raise Exception("Login did not succeed")

            # Step 3: Fetch the code from the query params.
            redirectLocation = resp.headers.get("location")
            url_parts = parse.urlparse(redirectLocation)
            query_parts = parse.parse_qs(url_parts.query)

            # Step 4: Fetch the JWT token through envoy
            json_data = {
                "client_id": "envoy-ui-1",
                "code": query_parts["code"][0],
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": login_data["redirectUri"],
            }
            _LOGGER.debug("Checking JWT on envoy with params %s", json_data)
            resp = await client.post(
                ENDPOINT_URL_GET_JWT.format(self.host),
                json=json_data,
                timeout=30,
            )

            if resp.status_code != 200:
                raise Exception(
                    f"Could not fetch access token from envoy; HTTP {resp.status_code}: {resp.text}"
                )

            return resp.json()["access_token"]

    async def _fetch_owner_token_json(self):
        """
        Try to fetch the owner token json from Enlighten API
        :return:
        """
        _LOGGER.debug("Fetching owner token")
        async with self.async_client as client:
            # login to Enlighten
            payload_login = {
                "user[email]": self.enlighten_user,
                "user[password]": self.enlighten_pass,
            }
            resp = await client.post(ENLIGHTEN_AUTH_URL, data=payload_login, timeout=30)
            if resp.status_code >= 400:
                raise Exception("Could not Authenticate via Enlighten")

            # now that we're in a logged in session, we can request the installer token
            login_data = resp.json()
            payload_token = {
                "session_id": login_data["session_id"],
                "serial_num": self.enlighten_serial_num,
                "username": self.enlighten_user,
            }
            resp = await client.post(
                ENLIGHTEN_TOKEN_URL, json=payload_token, timeout=30
            )
            if resp.status_code != 200:
                raise Exception("Could not get installer token")
            return resp.text

    async def _getEnphaseToken(self):
        # First attempt should be to auth using envoy token, as this could result in a installer token
        if not self.disable_installer_account_use:
            self._token = await self._fetch_envoy_token_json()
            self.envoy_token_fetch_attempted = True

            _LOGGER.debug("Envoy Token")
            if self._is_enphase_token_expired(self._token):
                raise Exception("Just received token already expired")

            if self.token_type != "installer":
                _LOGGER.warning(
                    "Received token is of type %s, disabling installer account usage",
                    self.token_type,
                )
                self.disable_installer_account_use = True

        else:
            self._token = await self._fetch_owner_token_json()
            _LOGGER.debug("Commissioned Token")

        if self._is_enphase_token_expired(self._token):
            raise Exception("Just received token already expired")

        # this is normally owner or installer
        _LOGGER.info("TOKEN TYPE: %s", self.token_type)

        await self._refresh_token_cookies()

    async def _refresh_token_cookies(self):
        """
        Refresh the client's cookie with the token (if valid)
        :returns True if cookie refreshed, False if it couldn't be
        """
        # Create HTTP Header
        self._authorization_header = {"Authorization": "Bearer " + self._token}

        # Fetch the Enphase Token status from the local Envoy
        token_validation = await self._async_post(
            ENDPOINT_URL_CHECK_JWT.format(self.host)
        )

        if token_validation.status_code == 200:
            # set the cookies for future clients
            self._cookies = token_validation.cookies

            # search for all cookies with session in the name (sessionId, session_id, etc)
            session_cookies = [k for k in self._cookies if "session" in k.lower()]
            if len(session_cookies) > 0:
                # We have a session id, so let's drop the auth header
                # to prevent any lookups for authentication (if any)
                _LOGGER.debug(
                    "We got a session cookie (%s), empty the auth header",
                    ",".join(session_cookies),
                )
                self._authorization_header = {}
            return True

        # token not valid if we get here
        return False

    def _is_enphase_token_expired(self, token):
        decode = jwt.decode(
            token, options={"verify_signature": False}, algorithms="ES256"
        )

        if decode.get("enphaseUser", None) != None:
            self.token_type = decode["enphaseUser"]  # owner or installer

        exp_epoch = decode["exp"]
        # allow a buffer so we can try and grab it sooner
        exp_epoch -= self.token_refresh_buffer_seconds
        exp_time = datetime.datetime.fromtimestamp(exp_epoch)
        if datetime.datetime.now() < exp_time:
            _LOGGER.debug("Token expires at: %s", exp_time)
            return False
        else:
            _LOGGER.debug("Token expired on: %s", exp_time)
            return True

    async def init_authentication(self):
        _LOGGER.debug("Checking Token value: %s", self._token)
        # Check if a token has already been retrieved
        if self._token == "":
            _LOGGER.debug("Found empty token: %s", self._token)
            await self._getEnphaseToken()
        else:
            _LOGGER.debug("Token is populated: %s", self._token)
            if self._is_enphase_token_expired(self._token):
                _LOGGER.debug("Found Expired token - Retrieving new token")
                await self._getEnphaseToken()
            else:
                await self._refresh_token_cookies()

    async def stream_reader(self, meter_callback=None, loop=None):
        # First, login, etc, make sure we have a token.
        await self.init_authentication()

        if not self.isMeteringEnabled or self.endpoint_type != ENVOY_MODEL_S:
            _LOGGER.debug(
                "Metering is not enabled or endpoint type '%s' not supported",
                self.endpoint_type,
            )
            return False

        # Now we're either authenticated, or execution stopped.
        url = ENDPOINT_URL_STREAM.format(self.host)
        _LOGGER.debug("Connecting to %s", url)

        try:
            _LOGGER.debug(
                "HTTP GET stream: %s: Header:%s Cookies:%s",
                url,
                self._authorization_header,
                self._cookies,
            )
            async with self.async_client.stream(
                "GET",
                url,
                headers=self._authorization_header,
                cookies=self._cookies,
            ) as response:
                if response.status_code in (401, 404):
                    await response.aread()
                    _LOGGER.warning(
                        "Could not load the stream, HTTP %s: %s",
                        response.status_code,
                        response.text,
                    )
                    # No access, lets stop reconnection.
                    return False

                if response.status_code != 200:
                    await response.aread()
                    _LOGGER.warning(
                        "Error while fetching meter stream; HTTP %s: %s",
                        response.status_code,
                        response.text,
                    )
                    return True  # keep retrying.

                self.is_receiving_realtime_data = True
                _LOGGER.debug("Starting to read chunks of data.")

                async for chunk in response.aiter_text():
                    if not chunk.startswith("data:"):
                        continue

                    try:
                        reading = json.loads(chunk[6:])
                    except JSONDecodeError:
                        _LOGGER.debug("Unable to decode json chunk: %s", chunk[6:])
                        continue

                    if meter_callback:
                        try:
                            meter_callback(StreamData(reading))
                        except Exception as e:
                            _LOGGER.exception("Unable to execute callback: %s", e)
                            raise
                    else:
                        print(StreamData(reading))

            return True
        except Exception as e:
            _LOGGER.exception("Realtime data error: %s", str(e))
        finally:
            _LOGGER.error("Stopped reading realtime data")
            self.is_receiving_realtime_data = False

    async def update_endpoints(self, endpoints=None):
        """Update one or more endpoints, and set the appropriate class attribute.

        If no endpoint provided, then it will determine the endpoints based on the EnvoyData class.
        If a endpoint is provided, it needs to be a list of registered endpoints"""
        if endpoints == None:
            endpoints = self.data.required_endpoints | self.required_endpoints

        _LOGGER.info("Updating endpoints %s", endpoints)
        for endpoint in endpoints:
            endpoint_settings = self.uri_registry.get(endpoint)
            if endpoint_settings == None:
                _LOGGER.error(f"No settings found for uri {endpoint}")
                continue

            if endpoint_settings.get("installer_required", False) and (
                (self.token_type != "installer" and self.envoy_token_fetch_attempted)
                or self.disable_installer_account_use
            ):
                _LOGGER.info(
                    "Skipping installer endpoint %s (got token %s and "
                    "disabled installer use: %s)",
                    endpoint,
                    self.token_type,
                    self.disable_installer_account_use,
                )
                continue

            endpoint_settings.setdefault("last_fetch", 0)
            time_since_last_fetch = time.time() - endpoint_settings["last_fetch"]
            if time_since_last_fetch > endpoint_settings["cache_time"]:
                _LOGGER.info(
                    "UPDATING ENDPOINT %s: %s", endpoint, endpoint_settings["url"]
                )
                endpoint_settings["last_fetch"] = time.time()
                await self._update_endpoint(
                    attr=endpoint,
                    url=endpoint_settings["url"],
                )
                _LOGGER.info(
                    "- FETCHING ENDPOINT %s TOOK %.4f seconds",
                    endpoint,
                    time.time() - endpoint_settings["last_fetch"],
                )

            if self.data:
                self.data.set_endpoint_data(endpoint, getattr(self, endpoint))

    async def getData(self, getInverters=True):
        """
        Fetch data from the endpoint and if inverters selected default
        to fetching inverter data.
        """
        await self.init_authentication()

        if not self.endpoint_type:
            await self.detect_model()

        if not self.get_inverters or not getInverters:
            return

        # Fetch inverter status and stuff, raise exception if unauthorized.
        await self.update_endpoints()  # fetch all remaining endpoints

        # Set boolean that initial update has completed. This will cause
        # the dataclass to all None results, and possibly discarding some
        # endpoints to be polled.
        self.data.initial_update_finished = True

        if self.endpoint_production_json_results.status_code == 401:
            self.endpoint_production_json_results.raise_for_status()

        return

    @property
    def isMeteringEnabled(self):
        return isinstance(self.data, EnvoyMeteredWithCT)

    async def detect_model(self):
        """Method to determine if the Envoy supports consumption values or only production."""
        # Fetch required endpoints for model detection
        await self.update_endpoints(["endpoint_production_json_results"])

        # If self.endpoint_production_json_results.status_code is set with
        # 401 then we will give an error
        if (
            self.endpoint_production_json_results
            and self.endpoint_production_json_results.status_code == 401
        ):
            raise RuntimeError(
                "Could not connect to Envoy model. "
                + "Appears your Envoy is running firmware that requires secure communcation. "
                + "Please enter in the needed Enlighten credentials during setup."
            )

        if (
            self.endpoint_production_json_results
            and self.endpoint_production_json_results.status_code == 200
            and has_production_and_consumption(
                self.endpoint_production_json_results.json()
            )
        ):
            self.endpoint_type = ENVOY_MODEL_S

        else:
            await self.update_endpoints(["endpoint_production_v1_results"])
            if (
                self.endpoint_production_v1_results
                and self.endpoint_production_v1_results.status_code == 200
            ):
                self.endpoint_type = ENVOY_MODEL_C  # Envoy-C, standard envoy

        if not self.endpoint_type:
            raise RuntimeError(
                "Could not connect or determine Envoy model. "
                + "Check that the device is up at 'https://"
                + self.host
                + "'."
            )

        # Configure the correct self.data
        self.data = getEnvoyDataClass(
            self.endpoint_type, self.endpoint_production_json_results.json()
        )(self)

    async def get_full_serial_number(self):
        """Method to get the Envoy serial number.
        Used once upon initialization or upon adding component into homeassistant"""
        response = await self._async_fetch_with_retry(
            f"https://{self.host}/info.xml",
            follow_redirects=True,
        )
        if not response.text:
            return None
        if "<sn>" in response.text:
            return response.text.split("<sn>")[1].split("</sn>")[0]

    def create_connect_errormessage(self):
        """Create error message if unable to connect to Envoy"""
        return (
            "Unable to connect to Envoy. "
            + "Check that the device is up at 'http://"
            + self.host
            + "'."
        )

    def create_json_errormessage(self):
        """Create error message if unable to parse JSON response"""
        return (
            "Got a response from '"
            + self.host
            + "', but metric could not be found. "
            + "Maybe your model of Envoy doesn't "
            + "support the requested metric."
        )

    def process_production_value(self, production):
        if not self.disable_negative_production or production == None:
            # return production as is (which is the default)
            return production

        # a limited negative production should not show (each relay uses about 3.5 watt,
        # so lets make sure we can add up to 4 relays)
        # If you have the CT the wrong way it will count negative, so if the negative
        # is too big, we should show that value regardless, so the end user is able to
        # see and detect this CT placement error.
        return 0 if -15 < production < 0 else production

    async def production(self):
        return self.process_production_value(self.data.get("production"))

    async def production_l1(self):
        return self.process_production_value(self.data.get("production_l1"))

    async def production_l2(self):
        return self.process_production_value(self.data.get("production_l2"))

    async def production_l3(self):
        return self.process_production_value(self.data.get("production_l3"))

    ## Below *_phase methods are for backward compatibility
    async def _async_getattr(self, key):
        return await getattr(self, key)()

    production_phase = _async_getattr
    consumption_phase = _async_getattr
    daily_production_phase = _async_getattr
    daily_consumption_phase = _async_getattr
    lifetime_production_phase = _async_getattr
    lifetime_consumption_phase = _async_getattr
    voltage_phase = _async_getattr

    async def set_production_power(self, power_on):
        if self.endpoint_production_power is not None:
            formatted_url = ENDPOINT_URL_PRODUCTION_POWER.format(self.host)
            power_forced_off = 0 if power_on else 1
            result = await self._async_put(
                formatted_url, data={"length": 1, "arr": [power_forced_off]}
            )
            # Make sure the next poll will update the endpoint.
            self._clear_endpoint_cache("endpoint_production_power")

    def run_stream(self):
        print("Reading stream...")
        loop = asyncio.get_event_loop()
        self.data = EnvoyMeteredWithCT(self)
        self.endpoint_type = ENVOY_MODEL_S
        data_results = loop.run_until_complete(
            asyncio.gather(self.stream_reader(), return_exceptions=False)
        )

    async def getDataLoop(self):
        # We iterate multiple times to see if the url caching works.
        await self.getData()

        print("First getData cycle completed, waiting 10 secs for second cycle.")
        await asyncio.sleep(10)
        await self.getData()

        print("Second getData cycle completed, waiting 10 secs for final cycle.")
        await asyncio.sleep(10)
        await self.getData()

    def run_in_console(self, test_data_folder=None, data_parser="EnvoyMeteredWithCT"):
        """If running this module directly, print all the values in the console."""
        import pprint

        print("Reading...")

        if test_data_folder:
            _parser_mapping = {
                "EnvoyStandard": EnvoyStandard,
                "EnvoyMetered": EnvoyMetered,
                "EnvoyMeteredWithCT": EnvoyMeteredWithCT,
            }
            print("- Using test data")
            self.data = _parser_mapping.get(data_parser)(self)
            self.data._read_test_data(test_data_folder)
            # pprint.pprint(self.data.all_values)
        else:
            loop = asyncio.get_event_loop()
            loop.run_until_complete(
                asyncio.gather(self.getDataLoop(), return_exceptions=False)
            )

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(
            asyncio.gather(
                self.production(),
                self.consumption(),
                self.daily_production(),
                self.daily_consumption(),
                self.lifetime_production(),
                self.lifetime_consumption(),
                self.inverters_production(),
                self.battery_storage(),
                self.production_power(),
                self.inverters_status(),
                self.relay_status(),
                self.envoy_info(),
                self.inverters_info(),
                self.relay_info(),
                self.grid_status(),
                self.production_phase("production_l1"),
                self.production_phase("production_l2"),
                self.production_phase("production_l3"),
                return_exceptions=False,
            )
        )
        fields = [
            "production",
            "consumption",
            "daily_production",
            "daily_consumption",
            "lifetime_production",
            "lifetime_consumption",
            "inverters_production",
            "battery_storage",
            "production_power",
            "inverters_status",
            "relay_status",
            "envoy_info",
            "inverters_info",
            "relay_info",
            "grid_status",
            "production_phase(l1)",
            "production_phase(l2)",
            "production_phase(l3)",
        ]
        pprint.pprint(dict(zip(fields, results)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Retrieve energy information from the Enphase Envoy device."
    )
    parser.add_argument(
        "-u", "--user", dest="enlighten_user", help="Enlighten Username", required=True
    )
    parser.add_argument(
        "-p", "--pass", dest="enlighten_pass", help="Enlighten Password", required=True
    )
    parser.add_argument(
        "-s",
        "--serialnum",
        dest="enlighten_serial_num",
        help="Enlighten Envoy Serial Number. Only used when Commissioned=True.",
        required=True,
    )
    parser.add_argument(
        "-d", "--debug", dest="debug", help="Enable debug logging", action="store_true"
    )
    parser.add_argument(
        dest="host",
        help="Envoy IP address or host name",
    )
    parser.add_argument(
        "--test-stream",
        dest="test_stream",
        help="test /stream/meter endpoint",
        action="store_true",
    )
    parser.add_argument(
        "--test-data",
        dest="test_data",
        help="Use test data, instead of pulling it directly from envoy (arg = test folder)",
    )
    parser.add_argument(
        "--data-parser",
        dest="data_parser",
        help="When using test data, then use this class as dataclass",
        choices=["EnvoyStandard", "EnvoyMetered", "EnvoyMeteredWithCT"],
        default="EnvoyMeteredWithCT",
    )

    parser.add_argument(
        "--disable-negative-production",
        dest="disable_negative_production",
        help="Disable negative production values",
        action="store_true",
    )
    parser.add_argument(
        "--disable-installer-account",
        dest="disable_installer_account_use",
        help="Disable installer account use",
        action="store_true",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    if args.debug:
        logging.getLogger().setLevel(level=logging.DEBUG)
        logging.getLogger("httpcore").setLevel(logging.INFO)
        logging.getLogger("httpx").setLevel(logging.INFO)

    TESTREADER = EnvoyReader(
        host=args.host,
        inverters=True,
        enlighten_user=args.enlighten_user,
        enlighten_pass=args.enlighten_pass,
        enlighten_serial_num=args.enlighten_serial_num,
        disable_negative_production=args.disable_negative_production,
        disable_installer_account_use=args.disable_installer_account_use,
    )
    if args.test_stream:
        TESTREADER.run_stream()
    else:
        TESTREADER.run_in_console(
            test_data_folder=args.test_data,
            data_parser=args.data_parser,
        )
