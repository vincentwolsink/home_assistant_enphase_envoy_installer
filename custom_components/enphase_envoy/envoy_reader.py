"""Module to read production and consumption values from an Enphase Envoy on the local network."""
import argparse
import asyncio
import datetime
import time
import logging
import jwt
import xmltodict
import httpx
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

ENVOY_MODEL_S = "PC"
ENVOY_MODEL_C = "P"

# paths for the enlighten installer token
ENLIGHTEN_AUTH_URL = "https://enlighten.enphaseenergy.com/login/login.json"
ENLIGHTEN_TOKEN_URL = "https://entrez.enphaseenergy.com/tokens"

_LOGGER = logging.getLogger(__name__)


def has_production_and_consumption(json):
    """Check if json has keys for both production and consumption."""
    return "production" in json and "consumption" in json


def has_metering_setup(json):
    """Check if Active Count of Production CTs (eim) installed is greater than one."""
    return json["production"][1]["activeCount"] > 0


class SwitchToHTTPS(Exception):
    pass


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
    ):
        """Init the EnvoyReader."""
        self.host = host.lower()
        self.get_inverters = inverters
        self.endpoint_type = None
        self.serial_number_last_six = None
        self.endpoint_production_json_results = None
        self.endpoint_production_v1_results = None
        self.endpoint_production_inverters = None
        self.endpoint_production_results = None
        self.endpoint_ensemble_json_results = None
        self.endpoint_home_json_results = None
        self.endpoint_devstatus = None
        self.endpoint_production_power = None
        self.endpoint_info_results = None
        self.endpoint_inventory_results = None
        self.isMeteringEnabled = False
        self._async_client = async_client
        self._authorization_header = None
        self._cookies = None
        self.enlighten_user = enlighten_user
        self.enlighten_pass = enlighten_pass
        self.commissioned = commissioned
        self.enlighten_serial_num = enlighten_serial_num
        self._token = ""
        self.token_refresh_buffer_seconds = token_refresh_buffer_seconds

    @property
    def async_client(self):
        """Return the httpx client."""
        return self._async_client or httpx.AsyncClient(verify=False)

    async def _update(self):
        """Update the data."""
        if self.endpoint_type == ENVOY_MODEL_S:
            await self._update_from_pc_endpoint()
        if self.endpoint_type == ENVOY_MODEL_C or (
            self.endpoint_type == ENVOY_MODEL_S and not self.isMeteringEnabled
        ):
            await self._update_from_p_endpoint()

        await self._update_from_installer_endpoint()
        await self._update_endpoint("endpoint_info_results", ENDPOINT_URL_INFO_XML)
        await self._update_endpoint(
            "endpoint_inventory_results", ENDPOINT_URL_INVENTORY
        )

    async def _update_from_pc_endpoint(self):
        """Update from PC endpoint."""
        await self._update_endpoint(
            "endpoint_production_json_results", ENDPOINT_URL_PRODUCTION_JSON
        )
        await self._update_endpoint(
            "endpoint_ensemble_json_results", ENDPOINT_URL_ENSEMBLE_INVENTORY
        )
        await self._update_endpoint(
            "endpoint_home_json_results", ENDPOINT_URL_HOME_JSON
        )

    async def _update_from_p_endpoint(self):
        """Update from P endpoint."""
        await self._update_endpoint(
            "endpoint_production_v1_results", ENDPOINT_URL_PRODUCTION_V1
        )

    async def _update_from_installer_endpoint(self):
        """Update from installer endpoint."""
        await self._update_endpoint(
            "endpoint_devstatus", ENDPOINT_URL_DEVSTATUS, only_on_success=True
        )
        await self._update_endpoint(
            "endpoint_production_power",
            ENDPOINT_URL_PRODUCTION_POWER,
            only_on_success=True,
        )

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
                        could_refresh_cookies = await self._refresh_token_cookies()
                        if not could_refresh_cookies:
                            await self._getEnphaseToken()
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

    async def _fetch_owner_token_json(self):
        """
        Try to fetch the owner token json from Enlighten API
        :return:
        """
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
        self._token = await self._fetch_owner_token_json()
        _LOGGER.debug("Commissioned Token")

        if self._is_enphase_token_expired(self._token):
            raise Exception("Just received token already expired")

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
            return True

        # token not valid if we get here
        return False

    def _is_enphase_token_expired(self, token):
        decode = jwt.decode(
            token, options={"verify_signature": False}, algorithms="ES256"
        )
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

    async def check_connection(self):
        """Check if the Envoy is reachable. Also check if HTTP or"""
        """HTTPS is needed."""
        _LOGGER.debug("Checking Host: %s", self.host)
        resp = await self._async_fetch_with_retry(
            ENDPOINT_URL_PRODUCTION_V1.format(self.host)
        )
        _LOGGER.debug("Check connection HTTP Code: %s", resp.status_code)
        if resp.status_code == 301:
            raise SwitchToHTTPS

    async def getData(self, getInverters=True):
        """Fetch data from the endpoint and if inverters selected default"""
        """to fetching inverter data."""

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

        if not self.endpoint_type:
            await self.detect_model()
        else:
            await self._update()

        if not self.get_inverters or not getInverters:
            return

        inverters_url = ENDPOINT_URL_PRODUCTION_INVERTERS.format(self.host)
        response = await self._async_fetch_with_retry(inverters_url)
        _LOGGER.debug(
            "Fetched from %s: %s: %s",
            inverters_url,
            response,
            response.text,
        )
        if response.status_code == 401:
            response.raise_for_status()
        self.endpoint_production_inverters = response
        return

    async def detect_model(self):
        """Method to determine if the Envoy supports consumption values or only production."""
        try:
            await self._update_from_pc_endpoint()
        except httpx.HTTPError:
            pass

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
            self.isMeteringEnabled = has_metering_setup(
                self.endpoint_production_json_results.json()
            )
            if not self.isMeteringEnabled:
                await self._update_from_p_endpoint()
            self.endpoint_type = ENVOY_MODEL_S

        if not self.endpoint_type:
            try:
                await self._update_from_p_endpoint()
            except httpx.HTTPError:
                pass
            if (
                self.endpoint_production_v1_results
                and self.endpoint_production_v1_results.status_code == 200
            ):
                self.endpoint_type = ENVOY_MODEL_C  # Envoy-C, production only

        if not self.endpoint_type:
            raise RuntimeError(
                "Could not connect or determine Envoy model. "
                + "Check that the device is up at 'https://"
                + self.host
                + "'."
            )

        await self._update_from_installer_endpoint()
        await self._update_endpoint("endpoint_info_results", ENDPOINT_URL_INFO_XML)
        await self._update_endpoint(
            "endpoint_inventory_results", ENDPOINT_URL_INVENTORY
        )

    async def get_full_serial_number(self):
        """Method to get the  Envoy serial number."""
        response = await self._async_fetch_with_retry(
            f"https://{self.host}/info.xml",
            follow_redirects=True,
        )
        if not response.text:
            return None
        if "<sn>" in response.text:
            return response.text.split("<sn>")[1].split("</sn>")[0]
        match = SERIAL_REGEX.search(response.text)
        if match:
            return match.group(1)

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

    async def production(self):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""

        if self.endpoint_type == ENVOY_MODEL_S:
            raw_json = self.endpoint_production_json_results.json()
            idx = 1 if self.isMeteringEnabled else 0
            production = raw_json["production"][idx]["wNow"]
        elif self.endpoint_type == ENVOY_MODEL_C:
            raw_json = self.endpoint_production_v1_results.json()
            production = raw_json["wattsNow"]
        return int(production)

    async def production_phase(self, phase):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""
        phase_map = {"production_l1": 0, "production_l2": 1, "production_l3": 2}

        if self.endpoint_type == ENVOY_MODEL_S:
            raw_json = self.endpoint_production_json_results.json()
            idx = 1 if self.isMeteringEnabled else 0
            try:
                return int(
                    raw_json["production"][idx]["lines"][phase_map[phase]]["wNow"]
                )
            except (KeyError, IndexError):
                return None

        return None

    async def consumption(self):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""

        """Only return data if Envoy supports Consumption"""
        if self.endpoint_type in ENVOY_MODEL_C:
            return None

        raw_json = self.endpoint_production_json_results.json()
        consumption = raw_json["consumption"][0]["wNow"]
        return int(consumption)

    async def consumption_phase(self, phase):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""
        phase_map = {"consumption_l1": 0, "consumption_l2": 1, "consumption_l3": 2}

        """Only return data if Envoy supports Consumption"""
        if self.endpoint_type in ENVOY_MODEL_C:
            return None

        raw_json = self.endpoint_production_json_results.json()
        try:
            return int(raw_json["consumption"][0]["lines"][phase_map[phase]]["wNow"])
        except (KeyError, IndexError):
            return None

    async def daily_production(self):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""

        if self.endpoint_type == ENVOY_MODEL_S and self.isMeteringEnabled:
            raw_json = self.endpoint_production_json_results.json()
            daily_production = raw_json["production"][1]["whToday"]
        elif self.endpoint_type == ENVOY_MODEL_C or (
            self.endpoint_type == ENVOY_MODEL_S and not self.isMeteringEnabled
        ):
            raw_json = self.endpoint_production_v1_results.json()
            daily_production = raw_json["wattHoursToday"]
        return int(daily_production)

    async def daily_production_phase(self, phase):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""
        phase_map = {
            "daily_production_l1": 0,
            "daily_production_l2": 1,
            "daily_production_l3": 2,
        }

        if self.endpoint_type == ENVOY_MODEL_S and self.isMeteringEnabled:
            raw_json = self.endpoint_production_json_results.json()
            idx = 1 if self.isMeteringEnabled else 0
            try:
                return int(
                    raw_json["production"][idx]["lines"][phase_map[phase]]["whToday"]
                )
            except (KeyError, IndexError):
                return None

        return None

    async def daily_consumption(self):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""

        """Only return data if Envoy supports Consumption"""
        if self.endpoint_type in ENVOY_MODEL_C:
            return None

        raw_json = self.endpoint_production_json_results.json()
        daily_consumption = raw_json["consumption"][0]["whToday"]
        return int(daily_consumption)

    async def daily_consumption_phase(self, phase):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""
        phase_map = {
            "daily_consumption_l1": 0,
            "daily_consumption_l2": 1,
            "daily_consumption_l3": 2,
        }

        """Only return data if Envoy supports Consumption"""
        if self.endpoint_type in ENVOY_MODEL_C:
            return None

        raw_json = self.endpoint_production_json_results.json()
        try:
            return int(raw_json["consumption"][0]["lines"][0]["whToday"])
        except (KeyError, IndexError):
            return None

    async def seven_days_production(self):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""

        if self.endpoint_type == ENVOY_MODEL_S and self.isMeteringEnabled:
            raw_json = self.endpoint_production_json_results.json()
            seven_days_production = raw_json["production"][1]["whLastSevenDays"]
        elif self.endpoint_type == ENVOY_MODEL_C or (
            self.endpoint_type == ENVOY_MODEL_S and not self.isMeteringEnabled
        ):
            raw_json = self.endpoint_production_v1_results.json()
            seven_days_production = raw_json["wattHoursSevenDays"]
        return int(seven_days_production)

    async def seven_days_consumption(self):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""

        """Only return data if Envoy supports Consumption"""
        if self.endpoint_type in ENVOY_MODEL_C:
            return None

        raw_json = self.endpoint_production_json_results.json()
        seven_days_consumption = raw_json["consumption"][0]["whLastSevenDays"]
        return int(seven_days_consumption)

    async def lifetime_production(self):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""

        if self.endpoint_type == ENVOY_MODEL_S and self.isMeteringEnabled:
            raw_json = self.endpoint_production_json_results.json()
            lifetime_production = raw_json["production"][1]["whLifetime"]
        elif self.endpoint_type == ENVOY_MODEL_C or (
            self.endpoint_type == ENVOY_MODEL_S and not self.isMeteringEnabled
        ):
            raw_json = self.endpoint_production_v1_results.json()
            lifetime_production = raw_json["wattHoursLifetime"]
        return int(lifetime_production)

    async def lifetime_production_phase(self, phase):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""
        phase_map = {
            "lifetime_production_l1": 0,
            "lifetime_production_l2": 1,
            "lifetime_production_l3": 2,
        }

        if self.endpoint_type == ENVOY_MODEL_S and self.isMeteringEnabled:
            raw_json = self.endpoint_production_json_results.json()
            idx = 1 if self.isMeteringEnabled else 0

            try:
                return int(
                    raw_json["production"][idx]["lines"][phase_map[phase]]["whLifetime"]
                )
            except (KeyError, IndexError):
                return None

        return None

    async def lifetime_consumption(self):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""

        """Only return data if Envoy supports Consumption"""
        if self.endpoint_type in ENVOY_MODEL_C:
            return None

        raw_json = self.endpoint_production_json_results.json()
        lifetime_consumption = raw_json["consumption"][0]["whLifetime"]
        return int(lifetime_consumption)

    async def lifetime_consumption_phase(self, phase):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""
        phase_map = {
            "lifetime_consumption_l1": 0,
            "lifetime_consumption_l2": 1,
            "lifetime_consumption_l3": 2,
        }

        """Only return data if Envoy supports Consumption"""
        if self.endpoint_type in ENVOY_MODEL_C:
            return None

        raw_json = self.endpoint_production_json_results.json()
        try:
            return int(
                raw_json["consumption"][0]["lines"][phase_map[phase]]["whLifetime"]
            )
        except (KeyError, IndexError):
            return None

    async def inverters_production(self):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""

        response_dict = {}
        try:
            for item in self.endpoint_production_inverters.json():
                response_dict[item["serialNumber"]] = {
                    "watt": item["lastReportWatts"],
                    "report_date": time.strftime(
                        "%Y-%m-%d %H:%M:%S", time.localtime(item["lastReportDate"])
                    ),
                }
        except (JSONDecodeError, KeyError, IndexError, TypeError, AttributeError):
            return None

        return response_dict

    async def battery_storage(self):
        """Return battery data from Envoys that support and have batteries installed"""
        try:
            raw_json = self.endpoint_production_json_results.json()
        except JSONDecodeError:
            return None

        """For Envoys that support batteries but do not have them installed the"""
        """percentFull will not be available in the JSON results. The API will"""
        """only return battery data if batteries are installed."""
        if "percentFull" not in raw_json["storage"][0].keys():
            # "ENCHARGE" batteries are part of the "ENSEMBLE" api instead
            # Check to see if it's there. Enphase has too much fun with these names
            if self.endpoint_ensemble_json_results is not None:
                ensemble_json = self.endpoint_ensemble_json_results.json()
                if len(ensemble_json) > 0 and "devices" in ensemble_json[0].keys():
                    return ensemble_json[0]["devices"]
            return None

        return raw_json["storage"][0]

    async def grid_status(self):
        """Return grid status reported by Envoy"""
        if self.endpoint_home_json_results is not None:
            home_json = self.endpoint_home_json_results.json()
            if (
                "enpower" in home_json.keys()
                and "grid_status" in home_json["enpower"].keys()
            ):
                return home_json["enpower"]["grid_status"]

        return None

    async def production_power(self):
        """Return production power status reported by Envoy"""
        if self.endpoint_production_power is not None:
            power_json = self.endpoint_production_power.json()
            if "powerForcedOff" in power_json.keys():
                return not power_json["powerForcedOff"]

        return None

    async def set_production_power(self, power_on):
        if self.endpoint_production_power is not None:
            formatted_url = ENDPOINT_URL_PRODUCTION_POWER.format(self.host)
            power_forced_off = 0 if power_on else 1
            result = await self._async_put(
                formatted_url, data={"length": 1, "arr": [power_forced_off]}
            )

    async def inverters_status(self):
        """Running getData() beforehand will set self.enpoint_type and self.isDataRetrieved"""
        """so that this method will only read data from stored variables"""
        response_dict = {}
        try:
            devstatus = self.endpoint_devstatus.json()
            for item in devstatus["pcu"]["values"]:
                if "serialNumber" in devstatus["pcu"]["fields"]:
                    if (
                        item[devstatus["pcu"]["fields"].index("devType")] == 12
                    ):  # this is a relay
                        continue

                    serial = item[devstatus["pcu"]["fields"].index("serialNumber")]

                    response_dict[serial] = {}

                    for field in [
                        "communicating",
                        "producing",
                        "reportDate",
                        "temperature",
                        "dcVoltageINmV",
                        "dcCurrentINmA",
                        "acVoltageINmV",
                        "acPowerINmW",
                    ]:
                        if field in devstatus["pcu"]["fields"]:
                            value = item[devstatus["pcu"]["fields"].index(field)]
                            if field == "reportDate":
                                response_dict[serial]["report_date"] = time.strftime(
                                    "%Y-%m-%d %H:%M:%S", time.localtime(value)
                                )
                            elif field == "dcVoltageINmV":
                                response_dict[serial]["dc_voltage"] = int(value) / 1000
                            elif field == "dcCurrentINmA":
                                response_dict[serial]["dc_current"] = int(value) / 1000
                            elif field == "acVoltageINmV":
                                response_dict[serial]["ac_voltage"] = int(value) / 1000
                            elif field == "acPowerINmW":
                                response_dict[serial]["ac_power"] = int(value) / 1000
                            else:
                                response_dict[serial][field] = value

        except (JSONDecodeError, KeyError, IndexError, TypeError, AttributeError):
            return None

        return response_dict

    async def relay_status(self):
        """Return relay status from Envoys that have relays installed."""
        response_dict = {}
        try:
            devstatus = self.endpoint_devstatus.json()
            for item in devstatus["pcu"]["values"]:
                if "serialNumber" in devstatus["pcu"]["fields"]:
                    if (
                        item[devstatus["pcu"]["fields"].index("devType")] != 12
                    ):  # this is a relay
                        continue

                    serial = item[devstatus["pcu"]["fields"].index("serialNumber")]
                    dev = response_dict.setdefault(serial, {})
                    for field in [
                        "communicating",
                        "reportDate",
                    ]:
                        if field in devstatus["pcu"]["fields"]:
                            value = item[devstatus["pcu"]["fields"].index(field)]
                            if field == "reportDate":
                                dev["report_date"] = time.strftime(
                                    "%Y-%m-%d %H:%M:%S", time.localtime(value)
                                )
                            else:
                                dev[field] = value

            for item in devstatus["nsrb"]["values"]:
                if "serialNumber" in devstatus["nsrb"]["fields"]:
                    serial = item[devstatus["nsrb"]["fields"].index("serialNumber")]
                    response_dict[serial] = {}
                    dev = response_dict.setdefault(serial, {})

                    for field in [
                        "relay",
                        "forced",
                        "reason_code",
                        "reason",
                    ]:
                        if field in devstatus["nsrb"]["fields"]:
                            value = item[devstatus["nsrb"]["fields"].index(field)]
                            dev[field] = value
        except (JSONDecodeError, KeyError, IndexError, TypeError, AttributeError):
            return None

        return response_dict

        return None

    async def envoy_info(self):
        device_data = {}

        if self.endpoint_home_json_results:
            home_json = self.endpoint_home_json_results.json()
            if "update_status" in home_json:
                device_data["update_status"] = home_json["update_status"]
                device_data["software_build_epoch"] = home_json["software_build_epoch"]

        if self.endpoint_info_results:
            try:
                data = xmltodict.parse(self.endpoint_info_results.text)
                device_data["software"] = data["envoy_info"]["device"]["software"]
                device_data["pn"] = data["envoy_info"]["device"]["pn"]
            except (KeyError, IndexError, TypeError, AttributeError):
                pass

        return device_data

    async def inverters_info(self):
        response_dict = {}
        try:
            devinfo = self.endpoint_inventory_results.json()
            for item in devinfo:
                if "type" in item and item["type"] == "PCU":
                    for device in item["devices"]:
                        if device["dev_type"] == 12:
                            # this is a relay
                            continue
                        response_dict[device["serial_num"]] = device
        except (KeyError, IndexError, TypeError, AttributeError):
            pass

        return response_dict

    def run_in_console(self):
        """If running this module directly, print all the values in the console."""
        print("Reading...")
        loop = asyncio.get_event_loop()
        data_results = loop.run_until_complete(
            asyncio.gather(self.getData(), return_exceptions=False)
        )

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(
            asyncio.gather(
                self.production(),
                self.consumption(),
                self.daily_production(),
                self.daily_consumption(),
                self.seven_days_production(),
                self.seven_days_consumption(),
                self.lifetime_production(),
                self.lifetime_consumption(),
                self.inverters_production(),
                self.battery_storage(),
                self.production_power(),
                self.inverters_status(),
                self.relay_status(),
                self.envoy_info(),
                self.inverters_info(),
                return_exceptions=False,
            )
        )

        print(f"production:              {results[0]}")
        print(f"consumption:             {results[1]}")
        print(f"daily_production:        {results[2]}")
        print(f"daily_consumption:       {results[3]}")
        print(f"seven_days_production:   {results[4]}")
        print(f"seven_days_consumption:  {results[5]}")
        print(f"lifetime_production:     {results[6]}")
        print(f"lifetime_consumption:    {results[7]}")
        print(f"inverters_production:    {results[8]}")
        print(f"battery_storage:         {results[9]}")
        print(f"production_power:        {results[10]}")
        print(f"inverters_status:        {results[11]}")
        print(f"relays:                  {results[12]}")
        print(f"envoy_info:              {results[13]}")
        print(f"inverters_info:          {results[14]}")


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
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    TESTREADER = EnvoyReader(
        host=args.host,
        inverters=True,
        enlighten_user=args.enlighten_user,
        enlighten_pass=args.enlighten_pass,
        enlighten_serial_num=args.enlighten_serial_num,
    )
    TESTREADER.run_in_console()
