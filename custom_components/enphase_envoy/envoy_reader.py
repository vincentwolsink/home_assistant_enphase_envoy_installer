"""Module to read production and consumption values from an Enphase Envoy on the local network."""

import asyncio
import datetime
import time
import logging
import jwt
import xmltodict
import httpx
import ipaddress
import json
import hashlib
import base64
import secrets
import string

from jsonpath import jsonpath
from functools import partial
from urllib import parse
from json.decoder import JSONDecodeError

from .envoy_endpoints import (
    ENDPOINT_URL_INFO_XML,
    ENDPOINT_URL_PRODUCTION_JSON,
    ENDPOINT_URL_PRODUCTION_V1,
    ENDPOINT_URL_PRODUCTION_INVERTERS,
    ENDPOINT_URL_PRODUCTION_REPORT,
    ENDPOINT_URL_PRODUCTION_POWER,
    ENDPOINT_URL_PDM_ENERGY,
    ENDPOINT_URL_STREAM,
    ENDPOINT_URL_ENSEMBLE_INVENTORY,
    ENDPOINT_URL_ENSEMBLE_SECCTRL,
    ENDPOINT_URL_ENSEMBLE_POWER,
    ENDPOINT_URL_INVENTORY,
    ENDPOINT_URL_COMM_STATUS,
    ENDPOINT_URL_DEVSTATUS,
    ENDPOINT_URL_INSTALLER_AGF,
    ENDPOINT_URL_INSTALLER_AGF_SET_PROFILE,
    ENDPOINT_URL_INSTALLER_AGF_UPLOAD_PROFILE,
    ENDPOINT_URL_ADMIN_TARIFF,
)

ENVOY_MODEL_M = "Metered"
ENVOY_MODEL_S = "Standard"

# paths for the enlighten installer token
ENLIGHTEN_AUTH_URL = "https://enlighten.enphaseenergy.com/login/login.json"
ENLIGHTEN_TOKEN_URL = "https://entrez.enphaseenergy.com/tokens"

# paths used for fetching enlighten token through envoy
ENLIGHTEN_LOGIN_URL = "https://entrez.enphaseenergy.com/login"
ENDPOINT_URL_GET_JWT = "https://{}/auth/get_jwt"
ENDPOINT_URL_CHECK_JWT = "https://{}/auth/check_jwt"

_LOGGER = logging.getLogger(__name__)


def random_content(length):
    chars = string.ascii_letters + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


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
                    yield "report_date", (
                        time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(value))
                        if value
                        else None
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


class EnvoyReaderError(Exception):
    pass


class EnlightenError(EnvoyReaderError):
    pass


class EnvoyError(EnvoyReaderError):
    pass


class FileData:
    def __init__(self, file):
        if file.endswith(".json"):
            self.content_type = "application/json"
            with open(file) as json_file:
                self.json_data = json.load(json_file)
                _LOGGER.debug(f"File '{file}' JSON data: {self.json_data}")
        elif file.endswith(".xml"):
            self.content_type = "application/xml"
            with open(file) as xml_file:
                self.text = xml_file.read()
                _LOGGER.debug(f"File '{file}' text: {self.text}")

    @property
    def status_code(self):
        return 200

    @property
    def headers(self):
        return {"content-type": self.content_type}

    def json(self):
        return self.json_data


class StreamData:
    class PhaseData:
        def __init__(self, phase_data):
            # https://en.wikipedia.org/wiki/AC_power explains the terms/units
            self.watts = phase_data["p"]  # wNow, active/real power, W
            self.amps = phase_data["i"]  # rmsCurrent, A
            self.volt_ampere = phase_data["s"]  # apparent_power, VA
            self.volt = phase_data["v"]  # rmsVoltage, V
            self.pf = phase_data["pf"]  # pwrFactor, PF
            self.hz = phase_data["f"]  # Frequency, Hz
            self.var = phase_data["q"]  # Reactive power, var (volt ampere reactive)

        def __str__(self):
            desc = "<Phase %s watts, %s volt, %s amps, %s va, %s hz, %s pf, %s var />"
            return desc % (
                self.watts,
                self.volt,
                self.amps,
                self.volt_ampere,
                self.hz,
                self.pf,
                self.var,
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


def _async_get_property(key):
    async def get(self):
        return self.data.get(key)

    return get


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
        if (
            cls.reader.token_type == "installer"
            and not cls.reader.disable_installer_account_use
            and installer
        ):
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

    envoy_pn_value = "endpoint_info.envoy_info.device.pn"
    has_integrated_meter_value = (
        "endpoint_info.envoy_info.device.imeter"  # true/false value
    )
    envoy_software_value = "endpoint_info.envoy_info.device.software"
    serial_number_value = "endpoint_info.envoy_info.device.sn"
    grid_profile_value = "endpoint_installer_agf.selected_profile"
    grid_profiles_available_value = "endpoint_installer_agf.profiles"

    @envoy_property()
    def envoy_info(self):
        return {
            "pn": self.get("envoy_pn"),
            "software": self.get("envoy_software"),
            "model": getattr(self, "ALIAS", self.__class__.__name__[5:]),
        }

    production_value = path_by_token(
        owner="endpoint_production_v1.wattsNow",
        installer="endpoint_pdm_energy.production.pcu.wattsNow",
    )
    daily_production_value = path_by_token(
        owner="endpoint_production_v1.wattHoursToday",
        installer="endpoint_pdm_energy.production.pcu.wattHoursToday",
    )
    lifetime_production_value = path_by_token(
        owner="endpoint_production_v1.wattHoursLifetime",
        installer="endpoint_pdm_energy.production.pcu.wattHoursLifetime",
    )

    @envoy_property(required_endpoint="endpoint_production_power")
    def production_power(self):
        """Return production power status reported by Envoy"""
        force_off = self._resolve_path("endpoint_production_power.powerForcedOff")
        if force_off != None:
            return not force_off

    @envoy_property(required_endpoint="endpoint_ensemble_inventory")
    def grid_status(self):
        grid_status = self._resolve_path(
            "endpoint_ensemble_inventory.[?(@.type=='ENPOWER')].devices[0].mains_oper_state"
        )
        if grid_status != None:
            return grid_status == "closed"

    inverters_data_value = path_by_token(
        owner="endpoint_production_inverters.[?(@.devType==1)]",
        installer="endpoint_devstatus.pcu[?(@.devType==1)]",
    )

    pcu_availability_value = "endpoint_pcu_comm_status"

    @envoy_property
    def inverters_production(self):
        # We will use the endpoint based on the token_type, which is automatically resolved by the inverters_data property
        data = self.get("inverters_data")

        def iter():
            if (
                self.reader.token_type == "installer"
                and not self.reader.disable_installer_account_use
            ):
                for item in data:
                    yield item["serialNumber"], {
                        "watt": item["ac_power"],
                        "report_date": item["report_date"],
                    }
            else:
                # endpoint_production_inverters endpoint
                for item in data:
                    yield item["serialNumber"], {
                        "watt": item["lastReportWatts"],
                        "report_date": time.strftime(
                            "%Y-%m-%d %H:%M:%S", time.localtime(item["lastReportDate"])
                        ),
                    }

        return dict(iter())

    @envoy_property(required_endpoint="endpoint_inventory")
    def inverters_info(self):
        return self._path_to_dict(
            "endpoint_inventory.[?(@.type=='PCU')].devices[?(@.dev_type==1)]",
            "serial_num",
        )

    @envoy_property(required_endpoint="endpoint_inventory")
    def relay_info(self):
        return self._path_to_dict(
            "endpoint_inventory.[?(@.type=='NSRB')].devices[?(@.dev_type==12)]",
            "serial_num",
        )

    @envoy_property(required_endpoint="endpoint_devstatus")
    def inverters_status(self):
        return self._path_to_dict(
            "endpoint_devstatus.pcu[?(@.devType==1)]",
            "serialNumber",
        )

    @envoy_property(required_endpoint="endpoint_devstatus")
    def relays(self):
        status = self._path_to_dict(
            [
                "endpoint_devstatus.pcu[?(@.devType==12)]",
                "endpoint_devstatus.nsrb",
            ],
            "serialNumber",
        )
        if not status:
            # fallback to the information which is available with owner token.
            status = self.get("relay_info")
        return status

    @envoy_property(required_endpoint="endpoint_ensemble_inventory")
    def batteries(self):
        battery_data = self._resolve_path("endpoint_ensemble_inventory[0].devices")

        if isinstance(battery_data, list) and len(battery_data) > 0:
            battery_dict = {}
            for item in battery_data:
                if "last_rpt_date" in item:
                    item["report_date"] = time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(item["last_rpt_date"])
                    )
                if "encharge_capacity" in item and "percentFull" in item:
                    item["encharge_available_energy"] = item["encharge_capacity"] * (
                        item["percentFull"] / 100
                    )
                battery_dict[item["serial_num"]] = item

            return battery_dict

    @envoy_property(required_endpoint="endpoint_ensemble_power")
    def batteries_power(self):
        return self._path_to_dict("endpoint_ensemble_power.devices:", "serial_num")

    @envoy_property(required_endpoint="endpoint_ensemble_power")
    def agg_batteries_power(self):
        batteries_data = self._resolve_path("endpoint_ensemble_power.devices:")
        if batteries_data:
            return int(sum(batt["real_power_mw"] for batt in batteries_data) / 1000)

    agg_batteries_capacity_value = (
        "endpoint_ensemble_secctrl.Enc_max_available_capacity"
    )
    agg_batteries_soc_value = "endpoint_ensemble_secctrl.ENC_agg_soc"
    agg_batteries_available_energy_value = (
        "endpoint_ensemble_secctrl.ENC_agg_avail_energy"
    )

    tariff_value = "endpoint_admin_tariff.tariff"
    storage_mode_value = "endpoint_admin_tariff.tariff.storage_settings.mode"
    storage_reserved_soc_value = (
        "endpoint_admin_tariff.tariff.storage_settings.reserved_soc"
    )
    storage_very_low_soc_value = (
        "endpoint_admin_tariff.tariff.storage_settings.very_low_soc"
    )
    storage_charge_from_grid_value = (
        "endpoint_admin_tariff.tariff.storage_settings.charge_from_grid"
    )


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

    _production = "endpoint_production_json.production[?(@.type=='inverters')]"
    production_value = _production + ".wNow"
    lifetime_production_value = path_by_token(
        owner=_production + ".whLifetime",
        installer="endpoint_pdm_energy.production.pcu.wattHoursLifetime",
    )
    daily_production_value = "endpoint_pdm_energy.production.pcu.wattHoursToday"

    _production_ct = (
        "endpoint_production_json.production[?(@.type=='eim' && @.activeCount > 0)]"
    )
    _consumption_ct = "endpoint_production_json.consumption[?(@.measurementType == 'total-consumption' && @.activeCount > 0)]"
    voltage_value = _production_ct + ".rmsVoltage"


class EnvoyMeteredWithCT(EnvoyMetered):
    """Adds CT based sensors, like current usage per phase"""

    ALIAS = "Metered (with CT)"

    def __new__(cls, reader, **kw):
        # Add phase CT production value attributes, as this class is
        # chosen when one production CT is enabled.
        for attr, path in {
            "production": ".currW",
            "lifetime_production": ".whDlvdCum",
            "voltage": ".rmsVoltage",
            "ampere": ".rmsCurrent",
            "apparent_power": ".apprntPwr",
            "power_factor": ".pwrFactor",
            "reactive_power": ".reactPwr",
            "frequency": ".freqHz",
        }.items():
            ct_path = "endpoint_production_report"
            setattr(cls, f"{attr}_value", f"{ct_path}.cumulative{path}")

            # Also create paths for all phases.
            for i, phase in enumerate(["l1", "l2", "l3"]):
                full_path = f"{ct_path}.lines[{i}]{path}"
                setattr(cls, f"{attr}_{phase}_value", full_path)

        setattr(
            cls,
            "daily_production_value",
            "endpoint_production_json.production[?(@.type=='eim')].whToday",
        )
        for i, phase in enumerate(["l1", "l2", "l3"]):
            setattr(
                cls,
                f"daily_production_{phase}_value",
                f"endpoint_production_json.production[?(@.type=='eim')].lines[{i}].whToday",
            )

        # When we're using the endpoint_production_report primarily, then the following
        # endpoint can be used way less frequently
        reader.uri_registry["endpoint_production_json"]["cache_time"] = 50
        reader.uri_registry["endpoint_production_inverters"]["cache_time"] = 290

        return EnvoyMetered.__new__(cls)


def get_envoydataclass(envoy_type, production_json):
    if envoy_type == ENVOY_MODEL_S:
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
        url("production_json", ENDPOINT_URL_PRODUCTION_JSON, cache=0)
        url("production_v1", ENDPOINT_URL_PRODUCTION_V1, cache=20)
        url("production_inverters", ENDPOINT_URL_PRODUCTION_INVERTERS, cache=20)
        url("ensemble_inventory", ENDPOINT_URL_ENSEMBLE_INVENTORY, cache=20)
        url("ensemble_secctrl", ENDPOINT_URL_ENSEMBLE_SECCTRL, cache=20)
        url("ensemble_power", ENDPOINT_URL_ENSEMBLE_POWER, cache=20)
        iurl("pcu_comm_status", ENDPOINT_URL_COMM_STATUS, cache=90)
        iurl("devstatus", ENDPOINT_URL_DEVSTATUS, cache=20)
        iurl("production_power", ENDPOINT_URL_PRODUCTION_POWER, cache=20)
        url("info", ENDPOINT_URL_INFO_XML, cache=86400)
        url("inventory", ENDPOINT_URL_INVENTORY, cache=300)
        url("production_report", ENDPOINT_URL_PRODUCTION_REPORT, cache=0)
        iurl("pdm_energy", ENDPOINT_URL_PDM_ENERGY)
        iurl("installer_agf", ENDPOINT_URL_INSTALLER_AGF)
        url("admin_tariff", ENDPOINT_URL_ADMIN_TARIFF, cache=20)

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
        if attr not in self.uri_registry[attr]:
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
        if url.startswith("https://"):
            formatted_url = url.format(self.host)
            response = await self._async_fetch_with_retry(
                formatted_url, follow_redirects=False
            )
            if not only_on_success or response.status_code == 200:
                setattr(self, attr, response)
        else:
            data = FileData(url)
            setattr(self, attr, data)

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
                            await self._get_enphase_token()

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
        except httpx.TransportError as e:
            _LOGGER.debug("TransportError: %s", e)
            raise e

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
        except httpx.TransportError as e:
            _LOGGER.debug("TransportError: %s", e)
            raise e

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
                raise EnlightenError("Could not Login via Enlighten")

            # we should expect a 302 redirect
            if resp.status_code != 302:
                raise EnlightenError("Login did not succeed")

            # Step 3: Fetch the code from the query params.
            redirect_location = resp.headers.get("location")
            url_parts = parse.urlparse(redirect_location)
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
                raise EnvoyError(
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
                raise EnlightenError("Could not Authenticate via Enlighten")

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
                raise EnlightenError("Could not get installer token")
            return resp.text

    async def _get_enphase_token(self):
        # First attempt should be to auth using envoy token, as this could result in a installer token
        if not self.disable_installer_account_use:
            self._token = await self._fetch_envoy_token_json()
            self.envoy_token_fetch_attempted = True

            _LOGGER.debug("Envoy Token")
            if self._is_enphase_token_expired(self._token):
                raise EnlightenError("Just received token already expired")

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
            raise EnlightenError("Just received token already expired")

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
            await self._get_enphase_token()
        else:
            _LOGGER.debug("Token is populated: %s", self._token)
            if self._is_enphase_token_expired(self._token):
                _LOGGER.debug("Found Expired token - Retrieving new token")
                await self._get_enphase_token()
            else:
                await self._refresh_token_cookies()

    async def stream_reader(self, meter_callback=None):
        # First, login, etc, make sure we have a token.
        await self.init_authentication()

        if not self.is_metering_enabled or self.endpoint_type != ENVOY_MODEL_M:
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

    async def get_data(self, get_inverters=True):
        """
        Fetch data from the endpoint and if inverters selected default
        to fetching inverter data.
        """
        await self.init_authentication()

        if not self.endpoint_type:
            await self.detect_model()

        if not self.get_inverters or not get_inverters:
            return

        # Fetch inverter status and stuff, raise exception if unauthorized.
        await self.update_endpoints()  # fetch all remaining endpoints

        # Set boolean that initial update has completed. This will cause
        # the dataclass to all None results, and possibly discarding some
        # endpoints to be polled.
        self.data.initial_update_finished = True

        if self.endpoint_production_json.status_code == 401:
            self.endpoint_production_json.raise_for_status()

    @property
    def all_values(self):
        def iter():
            for key, val in self.data.all_values.items():
                if key.startswith("production"):
                    yield key, self.process_production_value(val)
                else:
                    yield key, val

        return dict(iter())

    @property
    def is_metering_enabled(self):
        return isinstance(self.data, EnvoyMeteredWithCT)

    async def detect_model(self):
        """Method to determine if the Envoy supports consumption values or only production."""
        # Fetch required endpoints for model detection
        await self.update_endpoints(["endpoint_production_json"])

        # If self.endpoint_production_json.status_code is set with
        # 401 then we will give an error
        if (
            self.endpoint_production_json
            and self.endpoint_production_json.status_code == 401
        ):
            raise RuntimeError(
                "Could not connect to Envoy model. "
                + "Appears your Envoy is running firmware that requires secure communcation. "
                + "Please enter in the needed Enlighten credentials during setup."
            )

        if (
            self.endpoint_production_json
            and self.endpoint_production_json.status_code == 200
            and has_production_and_consumption(self.endpoint_production_json.json())
        ):
            self.endpoint_type = ENVOY_MODEL_M

        else:
            await self.update_endpoints(["endpoint_production_v1"])
            if (
                self.endpoint_production_v1
                and self.endpoint_production_v1.status_code == 200
            ):
                self.endpoint_type = ENVOY_MODEL_S

        if not self.endpoint_type:
            raise RuntimeError(
                "Could not connect or determine Envoy model. "
                + "Check that the device is up at 'https://"
                + self.host
                + "'."
            )

        # Configure the correct self.data
        self.data = get_envoydataclass(
            self.endpoint_type, self.endpoint_production_json.json()
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

    async def set_production_power(self, power_on):
        if self.endpoint_production_power is not None:
            formatted_url = ENDPOINT_URL_PRODUCTION_POWER.format(self.host)
            power_forced_off = 0 if power_on else 1
            await self._async_put(
                formatted_url, data={"length": 1, "arr": [power_forced_off]}
            )
            # Make sure the next poll will update the endpoint.
            self._clear_endpoint_cache("endpoint_production_power")

    async def set_grid_profile(self, profile_id):
        if self.endpoint_installer_agf is not None:
            formatted_url = ENDPOINT_URL_INSTALLER_AGF_SET_PROFILE.format(self.host)
            resp = await self._async_put(
                formatted_url, data={"selected_profile": profile_id}
            )

        if "accepted" not in resp.text:
            raise EnvoyError(
                f"Failed setting grid profile: {resp.json().get('message')} - {resp.json().get('reason')}"
            )

        self._clear_endpoint_cache("endpoint_installer_agf")
        return resp

    async def upload_grid_profile(self, file):
        if self.endpoint_installer_agf is not None:
            formatted_url = ENDPOINT_URL_INSTALLER_AGF_UPLOAD_PROFILE.format(self.host)
            resp = await self._async_post(
                formatted_url, files={"file": open(file, "rb")}
            )
            message = resp.json().get("message")
            if message != "success":
                raise EnvoyError(f"Failed uploading grid profile: {message}")

        self._clear_endpoint_cache("endpoint_installer_agf")
        return resp

    async def set_storage(self, storage_key, storage_value):
        if self.endpoint_admin_tariff is not None:
            formatted_url = ENDPOINT_URL_ADMIN_TARIFF.format(self.host)
            tariff = self.data.get("tariff")
            tariff["storage_settings"][storage_key] = storage_value

            await self._async_put(formatted_url, data={"tariff": tariff})
            # Make sure the next poll will update the endpoint.
            self._clear_endpoint_cache("endpoint_admin_tariff")

    def run_stream(self):
        print("Reading stream...")
        loop = asyncio.get_event_loop()
        self.data = EnvoyMeteredWithCT(self)
        self.endpoint_type = ENVOY_MODEL_M
        loop.run_until_complete(
            asyncio.gather(self.stream_reader(), return_exceptions=False)
        )

    async def get_data_loop(self, no_url_cache_loop=False):
        # We iterate multiple times to see if the url caching works.
        await self.get_data()
        if no_url_cache_loop:
            return

        print("First get_data cycle completed, waiting 10 secs for second cycle.")
        await asyncio.sleep(10)
        await self.get_data()

        print("Second get_data cycle completed, waiting 10 secs for final cycle.")
        await asyncio.sleep(10)
        await self.get_data()
