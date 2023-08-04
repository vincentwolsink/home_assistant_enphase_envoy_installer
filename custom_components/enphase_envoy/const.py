"""The enphase_envoy component."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntityDescription,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.switch import SwitchDeviceClass, SwitchEntityDescription
from homeassistant.const import (
    Platform,
    PERCENTAGE,
    UnitOfApparentPower,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfTemperature,
    POWER_VOLT_AMPERE_REACTIVE,
)

DOMAIN = "enphase_envoy"

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]

COORDINATOR = "coordinator"
NAME = "name"
READER = "reader"

DEFAULT_SCAN_INTERVAL = 60  # default in seconds
DEFAULT_REALTIME_UPDATE_THROTTLE = 10

CONF_SERIAL = "serial"

LIVE_UPDATEABLE_ENTITIES = "live-update-entities"
DISABLE_INSTALLER_ACCOUNT_USE = "disable_installer_account_use"
ENABLE_ADDITIONAL_METRICS = "enable_additional_metrics"
ADDITIONAL_METRICS = []

PRODUCT_ID_MAPPING = {
    "800-00598-r04": {"name": "IQ Relay 1-phase", "sku": "Q-RELAY-1P-INT"},
    "800-00597-r02": {"name": "IQ Relay 3-phase", "sku": "Q-RELAY-3P-INT"},
    "800-00654-r08": {"name": "Envoy-S-Metered-EU", "sku": "ENV-S-WM-230"},
    "800-00656-r06": {"name": "Envoy-S-Standard-EU", "sku": "ENV-S-WB-230"},
    "800-01359-r02": {"name": "IQ8+ Microinverter", "sku": "IQ8PLUS-72-M-INT"},
    "800-01736-r02": {"name": "IQ7+ Microinverter", "sku": "IQ7PLUS-72-M-INT"},
    "800-01127-r02": {"name": "IQ7A Microinverter", "sku": "IQ7A-72-M-INT"},
}


def resolve_product_mapping(product_id):
    if PRODUCT_ID_MAPPING.get(product_id, None) != None:
        return PRODUCT_ID_MAPPING[product_id]

    def id_iter():
        yield product_id.rsplit("-", 1)[0]
        yield product_id.split("-")[1]

    for match in id_iter():
        for key, product in PRODUCT_ID_MAPPING.items():
            if key == match or match in key:
                # Create alias for consecutive calls.
                PRODUCT_ID_MAPPING[match] = product
                return product


def resolve_hardware_id(hardware_id):
    info = resolve_product_mapping(hardware_id)
    if not info:
        return hardware_id

    return f"{info['sku']} ({hardware_id})"


def get_model_name(model, hardware_id):
    product = resolve_product_mapping(hardware_id)
    if product:
        return product["name"]
    return model


SENSORS = (
    SensorEntityDescription(
        key="production",
        name="Current Power Production",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
    ),
    SensorEntityDescription(
        key="daily_production",
        name="Today's Energy Production",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="lifetime_production",
        name="Lifetime Energy Production",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="consumption",
        name="Current Power Consumption",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="daily_consumption",
        name="Today's Energy Consumption",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="lifetime_consumption",
        name="Lifetime Energy Consumption",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="inverters",
        name="Production",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=0,
    ),
    SensorEntityDescription(
        key="inverters_ac_voltage",
        name="AC Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    SensorEntityDescription(
        key="inverters_dc_voltage",
        name="DC Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    SensorEntityDescription(
        key="inverters_dc_current",
        name="DC Current",
        icon="mdi:current-dc",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.CURRENT,
    ),
    SensorEntityDescription(
        key="inverters_temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
    ),
    SensorEntityDescription(
        key="batteries",
        name="Battery",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.BATTERY,
    ),
    SensorEntityDescription(
        key="total_battery_percentage",
        name="Total Battery Percentage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.BATTERY,
    ),
    SensorEntityDescription(
        key="current_battery_capacity",
        name="Current Battery Capacity",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="voltage",
        name="Current Voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    SensorEntityDescription(
        key=f"ampere",
        name=f"Current Amps",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.CURRENT,
    ),
    SensorEntityDescription(
        key=f"apparent_power",
        name=f"Apparent Power",
        native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.APPARENT_POWER,
    ),
)
ADDITIONAL_METRICS.extend(
    [
        "ampere",
        "apparent_power",
    ]
)

PHASE_SENSORS = []
for phase in ["l1", "l2", "l3"]:
    PHASE_SENSORS.extend(
        [
            SensorEntityDescription(
                key=f"production_{phase}",
                name=f"Current Power Production {phase.upper()}",
                native_unit_of_measurement=UnitOfPower.WATT,
                state_class=SensorStateClass.MEASUREMENT,
                device_class=SensorDeviceClass.POWER,
                suggested_display_precision=0,
            ),
            SensorEntityDescription(
                key=f"daily_production_{phase}",
                name=f"Today's Energy Production {phase.upper()}",
                native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
                state_class=SensorStateClass.TOTAL_INCREASING,
                device_class=SensorDeviceClass.ENERGY,
                suggested_display_precision=0,
            ),
            SensorEntityDescription(
                key=f"lifetime_production_{phase}",
                name=f"Lifetime Energy Production {phase.upper()}",
                native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
                state_class=SensorStateClass.TOTAL_INCREASING,
                device_class=SensorDeviceClass.ENERGY,
                suggested_display_precision=0,
            ),
            SensorEntityDescription(
                key=f"voltage_{phase}",
                name=f"Current Voltage {phase.upper()}",
                native_unit_of_measurement=UnitOfElectricPotential.VOLT,
                state_class=SensorStateClass.MEASUREMENT,
                device_class=SensorDeviceClass.VOLTAGE,
            ),
            SensorEntityDescription(
                key=f"ampere_{phase}",
                name=f"Current Amps {phase.upper()}",
                native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
                state_class=SensorStateClass.MEASUREMENT,
                device_class=SensorDeviceClass.CURRENT,
            ),
            SensorEntityDescription(
                key=f"apparent_power_{phase}",
                name=f"Apparent Power {phase.upper()}",
                native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
                state_class=SensorStateClass.MEASUREMENT,
                device_class=SensorDeviceClass.APPARENT_POWER,
            ),
            SensorEntityDescription(
                key=f"reactive_power_{phase}",
                name=f"Reactive Power {phase.upper()}",
                native_unit_of_measurement=POWER_VOLT_AMPERE_REACTIVE,
                state_class=SensorStateClass.MEASUREMENT,
                device_class=SensorDeviceClass.REACTIVE_POWER,
            ),
            SensorEntityDescription(
                key=f"frequency_{phase}",
                name=f"Frequency {phase.upper()}",
                native_unit_of_measurement=UnitOfFrequency.HERTZ,
                state_class=SensorStateClass.MEASUREMENT,
                device_class=SensorDeviceClass.FREQUENCY,
                suggested_display_precision=1,
            ),
            SensorEntityDescription(
                key=f"power_factor_{phase}",
                name=f"Power Factor {phase.upper()}",
                native_unit_of_measurement=None,
                state_class=SensorStateClass.MEASUREMENT,
                device_class=SensorDeviceClass.POWER_FACTOR,
                suggested_display_precision=2,
            ),
            #
            # Consumption entities
            #
            SensorEntityDescription(
                key=f"consumption_{phase}",
                name=f"Current Power Consumption {phase.upper()}",
                native_unit_of_measurement=UnitOfPower.WATT,
                state_class=SensorStateClass.MEASUREMENT,
                device_class=SensorDeviceClass.POWER,
                suggested_display_precision=0,
            ),
            SensorEntityDescription(
                key=f"daily_consumption_{phase}",
                name=f"Today's Energy Consumption {phase.upper()}",
                native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
                state_class=SensorStateClass.TOTAL_INCREASING,
                device_class=SensorDeviceClass.ENERGY,
                suggested_display_precision=0,
            ),
            SensorEntityDescription(
                key=f"lifetime_consumption_{phase}",
                name=f"Lifetime Energy Consumption {phase.upper()}",
                native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
                state_class=SensorStateClass.TOTAL_INCREASING,
                device_class=SensorDeviceClass.ENERGY,
                suggested_display_precision=0,
            ),
        ]
    )
    ADDITIONAL_METRICS.extend(
        [
            f"ampere_{phase}",
            f"apparent_power_{phase}",
            f"reactive_power_{phase}",
            f"frequency_{phase}",
            f"power_factor_{phase}",
        ]
    )

BINARY_SENSORS = (
    BinarySensorEntityDescription(
        key="inverters_producing",
        name="Producing",
        device_class=BinarySensorDeviceClass.POWER,
    ),
    BinarySensorEntityDescription(
        key="inverters_communicating",
        name="Communicating",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    BinarySensorEntityDescription(
        key="grid_status",
        name="Grid Status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    BinarySensorEntityDescription(
        key="relays",
        name="Contact",
        device_class=BinarySensorDeviceClass.POWER,
    ),
    BinarySensorEntityDescription(
        key="relays_communicating",
        name="Communicating",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    BinarySensorEntityDescription(
        key="relays_forced",
        name="Forced",
        device_class=BinarySensorDeviceClass.TAMPER,
    ),
    BinarySensorEntityDescription(
        key="firmware",
        name="Firmware",
        device_class=BinarySensorDeviceClass.UPDATE,
    ),
)

BATTERY_ENERGY_DISCHARGED_SENSOR = SensorEntityDescription(
    key="battery_energy_discharged",
    name="Battery Energy Discharged",
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
    state_class=SensorStateClass.TOTAL,
    device_class=SensorDeviceClass.ENERGY,
)

BATTERY_ENERGY_CHARGED_SENSOR = SensorEntityDescription(
    key="battery_energy_charged",
    name="Battery Energy Charged",
    native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
    state_class=SensorStateClass.TOTAL,
    device_class=SensorDeviceClass.ENERGY,
)

PRODUCION_POWER_SWITCH = SwitchEntityDescription(
    key="production_power",
    name="Production",
    device_class=SwitchDeviceClass.SWITCH,
)
