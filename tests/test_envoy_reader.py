"""Tests for EnvoyReader data parsing using file-based test data.

Imports envoy_reader directly to avoid pulling in the full homeassistant
dependency tree (same pattern as test_stream_staleness.py).
"""

import importlib
import json
import os
import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest

TEST_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test_data",
    "envoy_metered",
)

# ---- Import envoy_reader directly, bypassing __init__.py ----

_pkg_name = "custom_components.enphase_envoy"

if _pkg_name not in sys.modules:
    pkg = ModuleType(_pkg_name)
    pkg.__path__ = ["custom_components/enphase_envoy"]
    pkg.__package__ = _pkg_name
    sys.modules[_pkg_name] = pkg

for sub in ("const", "envoy_endpoints"):
    full = f"{_pkg_name}.{sub}"
    if full not in sys.modules:
        sys.modules[full] = MagicMock()

spec = importlib.util.spec_from_file_location(
    f"{_pkg_name}.envoy_reader",
    "custom_components/enphase_envoy/envoy_reader.py",
    submodule_search_locations=[],
)
envoy_reader_mod = importlib.util.module_from_spec(spec)
sys.modules[f"{_pkg_name}.envoy_reader"] = envoy_reader_mod
spec.loader.exec_module(envoy_reader_mod)

EnvoyReader = envoy_reader_mod.EnvoyReader
EnvoyData = envoy_reader_mod.EnvoyData
EnvoyStandard = envoy_reader_mod.EnvoyStandard
EnvoyMetered = envoy_reader_mod.EnvoyMetered
EnvoyMeteredWithCT = envoy_reader_mod.EnvoyMeteredWithCT
parse_devstatus = envoy_reader_mod.parse_devstatus
parse_devicedata = envoy_reader_mod.parse_devicedata
merge_metersdata = envoy_reader_mod.merge_metersdata
FileData = envoy_reader_mod.FileData
ENVOY_MODEL_M = envoy_reader_mod.ENVOY_MODEL_M
ENVOY_MODEL_S = envoy_reader_mod.ENVOY_MODEL_S

ENDPOINTS = {}
for fname in os.listdir(TEST_DATA_DIR):
    if fname.startswith("endpoint_") and fname.endswith((".json", ".xml")):
        key = fname.replace("endpoint_", "").replace(".json", "").replace(".xml", "")
        ENDPOINTS[key] = os.path.join(TEST_DATA_DIR, fname)

# Aliases so code-expected endpoints resolve to test data files
ENDPOINTS["admin_tariff"] = os.path.join(
    TEST_DATA_DIR, "endpoint_admin_lib_tariff.json"
)
ENDPOINTS["installer_agf"] = os.path.join(
    TEST_DATA_DIR, "endpoint_installer_agf_index_json.json"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_reader(token_type="owner"):
    reader = EnvoyReader(
        host="192.168.1.1",
        inverters=True,
        enlighten_user="test@example.com",
        enlighten_pass="test_pass",
        enlighten_serial_num="999999900879",
    )
    reader._authorization_header = {"Authorization": "Bearer test"}
    reader._cookies = {}
    reader.token_type = token_type

    reader.uri_registry = {}
    for key, url in ENDPOINTS.items():
        reader.register_url(
            f"endpoint_{key}",
            url=url,
            cache=0,
            installer_required=False,
            optional=False,
        )

    return reader


def load_all(reader):
    for attr, settings in reader.uri_registry.items():
        resp = FileData(settings["url"])
        setattr(reader, attr, resp)
        if reader.data:
            reader.data.set_endpoint_data(attr, resp)


# ===========================================================================
# Model detection
# ===========================================================================


class TestModelDetection:
    def test_info_has_meter_flag(self):
        reader = make_reader()
        data = EnvoyStandard(reader)
        resp = FileData(ENDPOINTS["info"])
        data.set_endpoint_data("endpoint_info", resp)
        assert data.get("has_integrated_meter") == "true"


# ===========================================================================
# EnvoyMeteredWithCT data
# ===========================================================================


class TestEnvoyMeteredWithCT:
    """EnvoyMeteredWithCT overrides production paths to use production_report."""

    def _setup(self, token_type="owner"):
        reader = make_reader(token_type)
        reader.data = EnvoyMeteredWithCT(reader)
        load_all(reader)
        return reader

    def test_production_from_report(self):
        r = self._setup()
        assert r.data.get("production") == 3366.764

    def test_daily_production_from_eim(self):
        r = self._setup()
        assert r.data.get("daily_production") == 21430.12

    def test_lifetime_production_from_report(self):
        r = self._setup()
        assert r.data.get("lifetime_production") == 1820876.754

    def test_voltage_from_report(self):
        r = self._setup()
        assert r.data.get("voltage") == 248.761

    def test_frequency(self):
        r = self._setup()
        assert r.data.get("frequency") == 50.00

    def test_power_factor(self):
        r = self._setup()
        assert r.data.get("power_factor") == 0.99

    def test_ampere(self):
        r = self._setup()
        assert r.data.get("ampere") == 13.691

    def test_apparent_power(self):
        r = self._setup()
        assert r.data.get("apparent_power") == 3406.287

    def test_reactive_power(self):
        r = self._setup()
        assert r.data.get("reactive_power") == 283.013

    def test_production_power_on(self):
        r = self._setup(token_type="installer")
        assert r.data.get("production_power") is True

    def test_meters_readings(self):
        r = self._setup()
        readings = r.data.get("meters_readings")
        assert isinstance(readings, list)
        assert len(readings) >= 3
        eids = {m["eid"] for m in readings}
        assert 704643328 in eids
        assert 704643584 in eids
        assert 704643840 in eids

    def test_consumption(self):
        r = self._setup()
        assert r.data.get("consumption") == 3441.236
        assert r.data.get("daily_consumption") == 1820822.12
        assert r.data.get("lifetime_consumption") == 1820822.12

    def test_consumption_l1(self):
        r = self._setup()
        assert r.data.get("consumption_l1") == 3441.236

    def test_net_consumption_none(self):
        r = self._setup()
        assert r.data.get("net_consumption") is None

    @pytest.mark.parametrize("phase", ["l2", "l3"])
    def test_phase_production_none_for_missing_phases(self, phase):
        r = self._setup()
        assert r.data.get(f"production_{phase}") is None

    def test_l1_phase_values(self):
        r = self._setup()
        assert r.data.get("production_l1") == 3366.764
        assert r.data.get("voltage_l1") == 248.761
        assert r.data.get("ampere_l1") == 13.691
        assert r.data.get("frequency_l1") == 50.0
        assert r.data.get("apparent_power_l1") == 3406.287
        assert r.data.get("reactive_power_l1") == 283.013
        assert r.data.get("power_factor_l1") == 0.99


# ===========================================================================
# EnvoyMetered (without CT)
# ===========================================================================


class TestEnvoyMetered:
    """EnvoyMetered uses production_json / pdm_energy for production."""

    def _setup(self):
        reader = make_reader()
        reader.data = EnvoyMetered(reader)
        load_all(reader)
        return reader

    def test_production_from_inverters(self):
        r = self._setup()
        assert r.data.get("production") == 2642

    def test_daily_production_from_pdm(self):
        r = self._setup()
        assert r.data.get("daily_production") == 14291

    def test_lifetime_production_from_inverters(self):
        r = self._setup()
        assert r.data.get("lifetime_production") == 836653

    def test_voltage(self):
        r = self._setup()
        assert r.data.get("voltage") == 248.393

    def test_consumption(self):
        r = self._setup()
        assert r.data.get("consumption") == 3441.236
        assert r.data.get("daily_consumption") == 1820822.12
        assert r.data.get("lifetime_consumption") == 1820822.12

    def test_consumption_l1(self):
        r = self._setup()
        assert r.data.get("consumption_l1") == 3441.236

    def test_net_consumption_none(self):
        r = self._setup()
        assert r.data.get("net_consumption") is None


# ===========================================================================
# Inverter data
# ===========================================================================


class TestInverterData:
    def _setup(self):
        reader = make_reader()
        reader.data = EnvoyMeteredWithCT(reader)
        load_all(reader)
        return reader

    def test_inverter_production_count(self):
        r = self._setup()
        invs = r.data.get("inverter_production")
        assert len(invs) == 14
        assert "999999913010" in invs
        assert invs["999999913010"]["lastReportWatts"] == 252

    def test_inverter_production_total_watts(self):
        r = self._setup()
        invs = r.data.get("inverter_production")
        total = sum(i["lastReportWatts"] for i in invs.values())
        assert total == 3321

    def test_inverter_info_count(self):
        r = self._setup()
        info = r.data.get("inverter_info")
        assert len(info) == 14
        assert "999999913010" in info

    def test_inverter_info_fields(self):
        r = self._setup()
        info = r.data.get("inverter_info")["999999913010"]
        assert info["img_pnum_running"] == "520-00082-r01-v04.27.04"
        assert info["part_num"] == "800-01736-r02"
        assert info["producing"] is True
        assert info["communicating"] is True

    def test_inverter_device_data_count(self):
        r = self._setup()
        dd = r.data.get("inverter_device_data")
        assert len(dd) == 12
        assert "999999913010" in dd

    def test_inverter_device_data_fields(self):
        r = self._setup()
        inv = r.data.get("inverter_device_data")["999999913010"]
        assert inv["type"] == "pcu"
        assert inv["sn"] == "999999913010"
        assert inv["active"] is True
        assert inv["gone"] is False
        assert inv["watts"] == 104
        assert inv["watts_max"] == 220
        assert inv["watt_hours_today"] == 59
        assert inv["temperature"] == 8
        assert inv["dc_voltage"] == 36.203
        assert inv["dc_current"] == 3.398
        assert inv["ac_voltage"] == 233.125
        assert inv["ac_current"] == 0.514
        assert inv["ac_frequency"] == 49.982
        assert inv["rssi"] == 104
        assert inv["issi"] == 66
        assert inv["lifetime_power"] == pytest.approx(752759.4, rel=0.01)
        assert inv["conversion_error"] == 0
        assert inv["conversion_error_cycles"] == 0
        assert inv["last_reading_interval"] == 908
        assert inv["last_reading"] == 1738574464

    def test_inverter_device_data_watt_hours(self):
        r = self._setup()
        inv = r.data.get("inverter_device_data")["999999913010"]
        assert inv["watt_hours_today"] == 59
        assert inv["watt_hours_yesterday"] == 1072
        assert inv["watt_hours_week"] == 4453

    def test_pcu_availability(self):
        r = make_reader(token_type="installer")
        r.data = EnvoyMeteredWithCT(r)
        load_all(r)
        val = r.data.get("pcu_availability")
        assert val is not None
        assert "999999913010" in val
        assert val["999999913010"] == 5


# ===========================================================================
# Relay data
# ===========================================================================


class TestRelayData:
    def _setup(self):
        reader = make_reader()
        reader.data = EnvoyMeteredWithCT(reader)
        load_all(reader)
        return reader

    def test_relay_info_count(self):
        r = self._setup()
        info = r.data.get("relay_info")
        assert len(info) == 2
        assert "999999968177" in info

    def test_relay_info_fields(self):
        r = self._setup()
        relay = r.data.get("relay_info")["999999968177"]
        assert relay["dev_type"] == 12
        assert relay["part_num"] == "800-00598-r04"
        assert relay["relay"] == "closed"
        assert relay["line1-connected"] is True
        assert relay["line2-connected"] is False
        assert relay["communicating"] is True
        assert relay["img_pnum_running"] == "520-00086-r01-v02.12.07"

    def test_relay_device_data_count(self):
        r = self._setup()
        dd = r.data.get("relay_device_data")
        assert len(dd) == 1
        assert "999999968177" in dd

    def test_relay_device_data_fields(self):
        r = self._setup()
        relay = r.data.get("relay_device_data")["999999968177"]
        assert relay["type"] == "nsrb"
        assert relay["sn"] == "999999968177"
        assert relay["temperature"] == 21
        assert relay["voltage_l1"] == 231.220
        assert relay["voltage_l2"] == 1.640
        assert relay["voltage_l3"] == 0.0
        assert relay["frequency"] == 49.976
        assert relay["state_change_count"] == 1


# ===========================================================================
# Battery data
# ===========================================================================


class TestBatteryData:
    def _setup(self):
        reader = make_reader()
        reader.data = EnvoyMeteredWithCT(reader)
        load_all(reader)
        return reader

    def test_battery_count(self):
        r = self._setup()
        bats = r.data.get("batteries")
        assert len(bats) == 3
        assert "999999995065" in bats

    def test_battery_fields(self):
        r = self._setup()
        b = r.data.get("batteries")["999999995065"]
        assert b["part_num"] == "830-01760-r46"
        assert b["percentFull"] == 20
        assert b["temperature"] == 20
        assert b["encharge_capacity"] == 3500
        assert b["encharge_available_energy"] == 700.0
        assert b["communicating"] is True
        assert b["operating"] is True
        assert b["led_status"] == 17

    def test_battery_report_date_formatted(self):
        r = self._setup()
        b = r.data.get("batteries")["999999995065"]
        assert b["report_date"] is not None
        assert "2024" in b["report_date"]

    def test_batteries_power(self):
        r = self._setup()
        power = r.data.get("batteries_power")
        assert len(power) == 3
        assert power["999999995065"]["real_power_mw"] == 179000

    def test_aggregated_battery_metrics(self):
        r = self._setup()
        assert r.data.get("agg_batteries_power") == 552
        assert r.data.get("agg_batteries_soc") == 89
        assert r.data.get("agg_batteries_capacity") == 10500
        assert r.data.get("agg_batteries_available_energy") == 9345

    def test_battery_firmware(self):
        r = self._setup()
        b = r.data.get("batteries")["999999995065"]
        assert b["img_pnum_running"] == "2.6.5973_rel/22.11"


# ===========================================================================
# Grid, storage, tariff
# ===========================================================================


class TestGridAndStorage:
    def _setup(self, token_type="owner"):
        reader = make_reader(token_type)
        reader.data = EnvoyMeteredWithCT(reader)
        load_all(reader)
        return reader

    def test_grid_profile(self):
        r = self._setup(token_type="installer")
        assert r.data.get("grid_profile") == "EN 50549-1:2019 RfG E02 Netherlands:1.3.2"

    def test_grid_profiles_available(self):
        r = self._setup(token_type="installer")
        assert isinstance(r.data.get("grid_profiles_available"), list)

    def test_polling_interval(self):
        r = self._setup(token_type="installer")
        assert r.data.get("polling_interval") == 900

    def test_storage_mode(self):
        r = self._setup()
        assert r.data.get("storage_mode") == "self-consumption"

    def test_storage_reserved_soc(self):
        r = self._setup()
        assert r.data.get("storage_reserved_soc") == 0

    def test_storage_charge_from_grid(self):
        r = self._setup()
        assert r.data.get("storage_charge_from_grid") is False

    def test_tariff(self):
        r = self._setup()
        t = r.data.get("tariff")
        assert t["currency"]["code"] == "EUR"
        assert t["storage_settings"]["mode"] == "self-consumption"

    def test_grid_status_closed(self):
        r = self._setup()
        assert r.data.get("grid_status") is True


# ===========================================================================
# DPEL
# ===========================================================================


class TestDPEL:
    def _setup(self):
        reader = make_reader(token_type="installer")
        reader.data = EnvoyMeteredWithCT(reader)
        load_all(reader)
        return reader

    def test_dpel_enabled(self):
        r = self._setup()
        assert r.data.get("dpel_enabled") is True

    def test_dpel_limit(self):
        r = self._setup()
        assert r.data.get("dpel_limit") == 50.0

    def test_dpel_mode_export(self):
        r = self._setup()
        assert r.data.get("dpel_mode") == "Export"


# ===========================================================================
# Envoy info
# ===========================================================================


class TestEnvoyInfo:
    def _setup(self):
        reader = make_reader()
        reader.data = EnvoyMeteredWithCT(reader)
        load_all(reader)
        return reader

    def test_serial_number(self):
        r = self._setup()
        assert r.data.get("serial_number") == "999999900879"

    def test_envoy_pn(self):
        r = self._setup()
        assert r.data.get("envoy_pn") == "800-00654-r08"

    def test_envoy_software(self):
        r = self._setup()
        assert r.data.get("envoy_software") == "D7.6.175"

    def test_envoy_info_dict(self):
        r = self._setup()
        info = r.data.get("envoy_info")
        assert info["pn"] == "800-00654-r08"
        assert info["software"] == "D7.6.175"
        assert info["model"] == "Metered (with CT)"

    def test_has_integrated_meter(self):
        r = self._setup()
        assert r.data.get("has_integrated_meter") == "true"

    def test_token_type(self):
        r = self._setup()
        assert r.data.get("token_type") == "owner"


# ===========================================================================
# all_values (full output dict)
# ===========================================================================


class TestAllValues:
    def _setup(self):
        reader = make_reader()
        reader.data = EnvoyMeteredWithCT(reader)
        load_all(reader)
        return reader

    def test_contains_all_expected_keys(self):
        r = self._setup()
        vals = r.all_values
        expected = {
            "production",
            "daily_production",
            "lifetime_production",
            "voltage",
            "envoy_info",
            "serial_number",
            "has_integrated_meter",
            "envoy_pn",
            "envoy_software",
            "batteries",
            "batteries_power",
            "agg_batteries_power",
            "agg_batteries_soc",
            "agg_batteries_capacity",
            "agg_batteries_available_energy",
            "inverter_production",
            "inverter_info",
            "inverter_device_data",
            "relay_device_data",
            "token_type",
        }
        for k in expected:
            assert k in vals, f"Missing: {k}"

    def test_production_not_negative(self):
        r = self._setup()
        r.disable_negative_production = True
        processed = r.process_production_value(r.data.get("production"))
        assert processed >= 0


# ===========================================================================
# set_endpoint_data
# ===========================================================================


class TestSetEndpointData:
    def test_json(self):
        reader = make_reader()
        data = EnvoyData(reader)
        resp = FileData(ENDPOINTS["production_json"])
        data.set_endpoint_data("endpoint_production_json", resp)
        assert (
            data.data["endpoint_production_json"]["production"][0]["type"]
            == "inverters"
        )

    def test_xml(self):
        reader = make_reader()
        data = EnvoyData(reader)
        resp = FileData(ENDPOINTS["info"])
        data.set_endpoint_data("endpoint_info", resp)
        assert (
            data.data["endpoint_info"]["envoy_info"]["device"]["sn"] == "999999900879"
        )

    def test_device_data_triggers_parse(self):
        reader = make_reader()
        data = EnvoyData(reader)
        resp = FileData(ENDPOINTS["device_data"])
        data.set_endpoint_data("endpoint_device_data", resp)
        assert "endpoint_device_data" in data.data
        assert len(data.data["endpoint_device_data"]) > 0

    def test_devstatus_triggers_parse(self):
        reader = make_reader()
        data = EnvoyData(reader)
        resp = FileData(ENDPOINTS["devstatus"])
        data.set_endpoint_data("endpoint_devstatus", resp)
        assert "endpoint_devstatus" in data.data
        assert len(data.data["endpoint_devstatus"]) > 0


# ===========================================================================
# process_production_value
# ===========================================================================


class TestProcessProductionValue:
    def test_positive_passes(self):
        r = make_reader()
        assert r.process_production_value(100) == 100

    def test_none_passes(self):
        r = make_reader()
        assert r.process_production_value(None) is None

    def test_disabled_returns_raw_negative(self):
        r = make_reader()
        r.disable_negative_production = False
        assert r.process_production_value(-5) == -5

    def test_small_negative_zeroed(self):
        r = make_reader()
        r.disable_negative_production = True
        assert r.process_production_value(-5) == 0

    def test_large_negative_passes(self):
        r = make_reader()
        r.disable_negative_production = True
        assert r.process_production_value(-20) == -20


# ===========================================================================
# Utility functions
# ===========================================================================


class TestParseDevstatus:
    def _load(self):
        with open(ENDPOINTS["devstatus"]) as f:
            return json.load(f)

    def test_returns_16_devices(self):
        result = parse_devstatus(self._load())
        assert len(result) == 16

    def test_includes_both_pcu_and_nsrb(self):
        result = parse_devstatus(self._load())
        types = {d["type"] for d in result}
        assert types == {"pcu", "nsrb"}

    def test_pcu_has_expected_fields(self):
        result = parse_devstatus(self._load())
        pcu = [d for d in result if d["type"] == "pcu"][0]
        assert "sn" in pcu
        assert "type" in pcu
        assert "temperature" in pcu
        assert "dc_voltage" in pcu
        assert "dc_current" in pcu
        assert "ac_voltage" in pcu
        assert "ac_power" in pcu
        assert "last_reading" in pcu
        assert "gone" in pcu

    def test_gone_field_negated(self):
        result = parse_devstatus(self._load())
        pcu = [d for d in result if d["type"] == "pcu"][0]
        assert pcu["gone"] is False


class TestParseDevicedata:
    def _load(self):
        with open(ENDPOINTS["device_data"]) as f:
            return json.load(f)

    def test_pcu_count(self):
        result = parse_devicedata(self._load())
        assert len([d for d in result if d["type"] == "pcu"]) == 12

    def test_nsrb_count(self):
        result = parse_devicedata(self._load())
        assert len([d for d in result if d["type"] == "nsrb"]) == 1

    def test_pcu_has_all_fields(self):
        result = parse_devicedata(self._load())
        pcu = [d for d in result if d["type"] == "pcu"][0]
        for f in (
            "sn",
            "watts",
            "watt_hours_today",
            "dc_voltage",
            "dc_current",
            "ac_voltage",
            "ac_current",
            "temperature",
            "rssi",
            "lifetime_power",
        ):
            assert f in pcu, f"Missing: {f}"

    def test_nsrb_fields(self):
        result = parse_devicedata(self._load())
        nsrb = [d for d in result if d["type"] == "nsrb"][0]
        assert nsrb["sn"] == "999999968177"
        assert nsrb["voltage_l1"] == 231.220
        assert nsrb["voltage_l2"] == 1.640
        assert nsrb["voltage_l3"] == 0.0


class TestMergeMetersdata:
    def test_updates_existing_eid(self):
        d1 = [{"eid": 1, "a": 1}, {"eid": 2, "a": 2}]
        d2 = [{"eid": 2, "b": 3}]
        result = merge_metersdata(d1, d2)
        assert len(result) == 2
        assert result[1]["b"] == 3

    def test_appends_new_eid(self):
        d1 = [{"eid": 1, "a": 1}]
        d2 = [{"eid": 2, "b": 2}]
        result = merge_metersdata(d1, d2)
        assert len(result) == 2

    def test_empty_source(self):
        result = merge_metersdata([], [{"eid": 1, "a": 1}])
        assert len(result) == 1

    def test_empty_addition(self):
        result = merge_metersdata([{"eid": 1, "a": 1}], [])
        assert len(result) == 1


# ===========================================================================
# Endpoint registration
# ===========================================================================


class TestEndpointRegistration:
    def test_all_endpoints_registered(self):
        reader = make_reader()
        expected = {f"endpoint_{k}" for k in ENDPOINTS}
        for ep in expected:
            assert ep in reader.uri_registry, f"Missing endpoint: {ep}"
