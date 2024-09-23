TEST_DATA = "/config/custom_components/enphase_envoy/test_data/envoy_metered/"
ENVOY_ENDPOINTS = {
    # Generic endpoints
    "info": {
        "url": TEST_DATA + "endpoint_info.xml",
        "cache": 20,
        "installer_required": False,
        "optional": False,
    },
    # Production/consumption endpoints
    "production_json": {
        "url": TEST_DATA + "endpoint_production_json.json",
        "cache": 0,
        "installer_required": False,
        "optional": False,
    },
    "production_v1": {
        "url": TEST_DATA + "endpoint_production_v1.json",
        "cache": 20,
        "installer_required": False,
        "optional": False,
    },
    "production_inverters": {
        "url": TEST_DATA + "endpoint_production_inverters.json",
        "cache": 20,
        "installer_required": False,
        "optional": False,
    },
    "production_report": {
        "url": TEST_DATA + "endpoint_production_report.json",
        "cache": 0,
        "installer_required": False,
        "optional": False,
    },
    "production_power": {
        "url": TEST_DATA + "endpoint_production_power.json",
        "cache": 20,
        "installer_required": False,
        "optional": True,
    },
    "pdm_energy": {
        "url": TEST_DATA + "endpoint_pdm_energy.json",
        "cache": 20,
        "installer_required": True,
        "optional": False,
    },
    # Battery endpoints
    "ensemble_inventory": {
        "url": TEST_DATA + "endpoint_ensemble_inventory.json",
        "cache": 20,
        "installer_required": False,
        "optional": True,
    },
    "ensemble_secctrl": {
        "url": TEST_DATA + "endpoint_ensemble_secctrl.json",
        "cache": 20,
        "installer_required": False,
        "optional": True,
    },
    "ensemble_power": {
        "url": TEST_DATA + "endpoint_ensemble_power.json",
        "cache": 20,
        "installer_required": False,
        "optional": True,
    },
    # Inverter endpoints
    "inventory": {
        "url": TEST_DATA + "endpoint_inventory.json",
        "cache": 300,
        "installer_required": False,
        "optional": False,
    },
    "devstatus": {
        "url": TEST_DATA + "endpoint_devstatus.json",
        "cache": 20,
        "installer_required": True,
        "optional": False,
    },
    "pcu_comm_check": {
        "url": TEST_DATA + "endpoint_pcu_comm_check.json",
        "cache": 90,
        "installer_required": True,
        "optional": True,
    },
    # Netprofile endpoints
    "installer_agf": {
        "url": TEST_DATA + "endpoint_installer_agf_index_json.json",
        "cache": 10,
        "installer_required": True,
        "optional": True,
    },
    # Tariff endpoints
    "admin_tariff": {
        "url": TEST_DATA + "endpoint_admin_lib_tariff.json",
        "cache": 10,
        "installer_required": False,
        "optional": True,
    },
}

ENDPOINT_URL_STREAM = None
ENDPOINT_URL_INSTALLER_AGF_SET_PROFILE = None
ENDPOINT_URL_INSTALLER_AGF_UPLOAD_PROFILE = None
