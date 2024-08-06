# Generic endpoints
ENDPOINT_URL_HOME_JSON = "https://{}/home.json"
ENDPOINT_URL_INFO_XML = "https://{}/info.xml"

# Production/consumption endpoints
ENDPOINT_URL_PRODUCTION_JSON = "https://{}/production.json?details=1"
ENDPOINT_URL_PRODUCTION_V1 = "https://{}/api/v1/production"
ENDPOINT_URL_PRODUCTION_INVERTERS = "https://{}/api/v1/production/inverters"
ENDPOINT_URL_PRODUCTION_REPORT = "https://{}/ivp/meters/reports/production"
ENDPOINT_URL_PRODUCTION_POWER = "https://{}/ivp/mod/603980032/mode/power"
ENDPOINT_URL_PDM_ENERGY = "https://{}/ivp/pdm/energy"
ENDPOINT_URL_STREAM = "https://{}/stream/meter"

# Battery endpoints
ENDPOINT_URL_ENSEMBLE_INVENTORY = "https://{}/ivp/ensemble/inventory"
ENDPOINT_URL_ENSEMBLE_SECCTRL = "https://{}/ivp/ensemble/secctrl"
ENDPOINT_URL_ENSEMBLE_POWER = "https://{}/ivp/ensemble/power"

# Inverter endpoints
ENDPOINT_URL_INVENTORY = "https://{}/inventory.json"
ENDPOINT_URL_DEVSTATUS = "https://{}/ivp/peb/devstatus"
ENDPOINT_URL_COMM_STATUS = "https://{}/installer/pcu_comm_check"

# Netprofile endpoints
ENDPOINT_URL_INSTALLER_AGF = "https://{}/installer/agf/index.json"
ENDPOINT_URL_INSTALLER_AGF_SET_PROFILE = "https://{}/installer/agf/set_profile.json"
ENDPOINT_URL_INSTALLER_AGF_UPLOAD_PROFILE = (
    "https://{}/installer/agf/upload_profile_package"
)

# Tariff endpoints
ENDPOINT_URL_ADMIN_TARIFF = "https://{}/admin/lib/tariff"
