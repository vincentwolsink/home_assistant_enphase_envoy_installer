ENVOY_ENDPOINTS = {
    # Generic endpoints
    "info": {
        "url": "https://{}/info.xml",
        "cache": 3600,
        "installer_required": False,
        "optional": False,
    },
    # Production/consumption endpoints
    "production_json": {
        "url": "https://{}/production.json?details=1",
        "cache": 0,
        "installer_required": False,
        "optional": False,
    },
    "production_v1": {
        "url": "https://{}/api/v1/production",
        "cache": 0,
        "installer_required": False,
        "optional": False,
    },
    "production_inverters": {
        "url": "https://{}/api/v1/production/inverters",
        "cache": 0,
        "installer_required": False,
        "optional": False,
    },
    "production_report": {
        "url": "https://{}/ivp/meters/reports/production",
        "cache": 0,
        "installer_required": False,
        "optional": False,
    },
    "production_power": {
        "url": "https://{}/ivp/mod/603980032/mode/power",
        "cache": 0,
        "installer_required": True,
        "optional": True,
    },
    "pdm_energy": {
        "url": "https://{}/ivp/pdm/energy",
        "cache": 0,
        "installer_required": True,
        "optional": False,
    },
    # Battery endpoints
    "ensemble_inventory": {
        "url": "https://{}/ivp/ensemble/inventory",
        "cache": 0,
        "installer_required": False,
        "optional": True,
    },
    "ensemble_secctrl": {
        "url": "https://{}/ivp/ensemble/secctrl",
        "cache": 0,
        "installer_required": False,
        "optional": True,
    },
    "ensemble_power": {
        "url": "https://{}/ivp/ensemble/power",
        "cache": 0,
        "installer_required": False,
        "optional": True,
    },
    # Inverter endpoints
    "inventory": {
        "url": "https://{}/inventory.json",
        "cache": 0,
        "installer_required": False,
        "optional": False,
    },
    "devstatus": {
        "url": "https://{}/ivp/peb/devstatus",
        "cache": 0,
        "installer_required": True,
        "optional": False,
    },
    "pcu_comm_check": {
        "url": "https://{}/installer/pcu_comm_check",
        "cache": 3600,
        "installer_required": True,
        "optional": True,
    },
    # Netprofile endpoints
    "installer_agf": {
        "url": "https://{}/installer/agf/index.json",
        "cache": 3600,
        "installer_required": True,
        "optional": True,
    },
    # Tariff endpoints
    "admin_tariff": {
        "url": "https://{}/admin/lib/tariff",
        "cache": 300,
        "installer_required": False,
        "optional": True,
    },
}

ENDPOINT_URL_STREAM = "https://{}/stream/meter"
ENDPOINT_URL_INSTALLER_AGF_SET_PROFILE = "https://{}/installer/agf/set_profile.json"
ENDPOINT_URL_INSTALLER_AGF_UPLOAD_PROFILE = (
    "https://{}/installer/agf/upload_profile_package"
)
