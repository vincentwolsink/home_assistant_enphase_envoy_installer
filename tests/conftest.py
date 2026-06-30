import os
from unittest.mock import AsyncMock

import pytest

TEST_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "test_data",
    "envoy_metered",
)

ENDPOINTS = {
    "info": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_info.xml"),
        "cache": 3600,
        "installer_required": False,
        "optional": False,
    },
    "peb_newscan": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_peb_newscan.json"),
        "cache": 3600,
        "installer_required": True,
        "optional": True,
    },
    "dpel": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_dpel.json"),
        "cache": 0,
        "installer_required": True,
        "optional": True,
    },
    "production_json": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_production_json.json"),
        "cache": 0,
        "installer_required": False,
        "optional": False,
    },
    "production_v1": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_production_v1.json"),
        "cache": 0,
        "installer_required": False,
        "optional": False,
    },
    "production_inverters": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_production_inverters.json"),
        "cache": 0,
        "installer_required": False,
        "optional": False,
    },
    "production_report": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_production_report.json"),
        "cache": 0,
        "installer_required": False,
        "optional": False,
    },
    "production_power": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_production_power.json"),
        "cache": 0,
        "installer_required": True,
        "optional": True,
    },
    "pdm_energy": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_pdm_energy.json"),
        "cache": 0,
        "installer_required": True,
        "optional": False,
    },
    "ensemble_inventory": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_ensemble_inventory.json"),
        "cache": 0,
        "installer_required": False,
        "optional": True,
    },
    "ensemble_secctrl": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_ensemble_secctrl.json"),
        "cache": 0,
        "installer_required": False,
        "optional": True,
    },
    "ensemble_power": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_ensemble_power.json"),
        "cache": 0,
        "installer_required": False,
        "optional": True,
    },
    "inventory": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_inventory.json"),
        "cache": 0,
        "installer_required": False,
        "optional": False,
    },
    "device_data": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_device_data.json"),
        "cache": 0,
        "installer_required": False,
        "optional": True,
    },
    "devstatus": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_devstatus.json"),
        "cache": 0,
        "installer_required": True,
        "optional": True,
    },
    "pcu_comm_check": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_pcu_comm_check.json"),
        "cache": 3600,
        "installer_required": True,
        "optional": True,
    },
    "meters": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_meters.json"),
        "cache": 0,
        "installer_required": False,
        "optional": False,
    },
    "meters_readings": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_meters_readings.json"),
        "cache": 0,
        "installer_required": False,
        "optional": True,
    },
    "installer_agf": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_installer_agf_index_json.json"),
        "cache": 3600,
        "installer_required": True,
        "optional": True,
    },
    "admin_tariff": {
        "url": os.path.join(TEST_DATA_DIR, "endpoint_admin_lib_tariff.json"),
        "cache": 300,
        "installer_required": False,
        "optional": True,
    },
}


@pytest.fixture
def envoy_reader():
    from custom_components.enphase_envoy.envoy_reader import EnvoyReader

    reader = EnvoyReader(
        host="192.168.1.1",
        inverters=True,
        enlighten_user="test@example.com",
        enlighten_pass="test_pass",
        enlighten_serial_num="999999900879",
    )

    reader._authorization_header = {"Authorization": "Bearer test"}
    reader._cookies = {}
    reader.init_authentication = AsyncMock()
    reader.token_type = "owner"

    reader.uri_registry = {}
    for key, endpoint in ENDPOINTS.items():
        reader.register_url(f"endpoint_{key}", **endpoint)

    return reader


@pytest.fixture
def envoy_reader_installer():
    from custom_components.enphase_envoy.envoy_reader import EnvoyReader

    reader = EnvoyReader(
        host="192.168.1.1",
        inverters=True,
        enlighten_user="test@example.com",
        enlighten_pass="test_pass",
        enlighten_serial_num="999999900879",
    )

    reader._authorization_header = {"Authorization": "Bearer test"}
    reader._cookies = {}
    reader.init_authentication = AsyncMock()
    reader.token_type = "installer"

    reader.uri_registry = {}
    for key, endpoint in ENDPOINTS.items():
        reader.register_url(f"endpoint_{key}", **endpoint)

    return reader
