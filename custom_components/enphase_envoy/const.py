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
    UnitOfEnergy,
    UnitOfPower,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfTemperature,
)

DOMAIN = "enphase_envoy"

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]

ICON = "mdi:flash"

COORDINATOR = "coordinator"
NAME = "name"
READER = "reader"

DEFAULT_SCAN_INTERVAL = 60  # default in seconds
DEFAULT_REALTIME_UPDATE_THROTTLE = 10

CONF_SERIAL = "serial"

LIVE_UPDATEABLE_ENTITIES = "live-update-entities"
DISABLE_INSTALLER_ACCOUNT_USE = "disable_installer_account_use"

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
    ),
    SensorEntityDescription(
        key="lifetime_production",
        name="Lifetime Energy Production",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="consumption",
        name="Current Power Consumption",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
    ),
    SensorEntityDescription(
        key="daily_consumption",
        name="Today's Energy Consumption",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="lifetime_consumption",
        name="Lifetime Energy Consumption",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="inverters",
        name="Production",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
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
)

PHASE_SENSORS = (
    SensorEntityDescription(
        key="production_l1",
        name="Current Power Production L1",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
    ),
    SensorEntityDescription(
        key="daily_production_l1",
        name="Today's Energy Production L1",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="lifetime_production_l1",
        name="Lifetime Energy Production L1",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="voltage_l1",
        name="Current Voltage L1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    SensorEntityDescription(
        key="production_l2",
        name="Current Power Production L2",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
    ),
    SensorEntityDescription(
        key="daily_production_l2",
        name="Today's Energy Production L2",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="lifetime_production_l2",
        name="Lifetime Energy Production L2",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="voltage_l2",
        name="Current Voltage L2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    SensorEntityDescription(
        key="production_l3",
        name="Current Power Production L3",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
    ),
    SensorEntityDescription(
        key="daily_production_l3",
        name="Today's Energy Production L3",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="lifetime_production_l3",
        name="Lifetime Energy Production L3",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="voltage_l3",
        name="Current Voltage L3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.VOLTAGE,
    ),
    SensorEntityDescription(
        key="consumption_l1",
        name="Current Power Consumption L1",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
    ),
    SensorEntityDescription(
        key="daily_consumption_l1",
        name="Today's Energy Consumption L1",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="lifetime_consumption_l1",
        name="Lifetime Energy Consumption L1",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="consumption_l2",
        name="Current Power Consumption L2",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
    ),
    SensorEntityDescription(
        key="daily_consumption_l2",
        name="Today's Energy Consumption L2",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="lifetime_consumption_l2",
        name="Lifetime Energy Consumption L2",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="consumption_l3",
        name="Current Power Consumption L3",
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER,
    ),
    SensorEntityDescription(
        key="daily_consumption_l3",
        name="Today's Energy Consumption L3",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SensorEntityDescription(
        key="lifetime_consumption_l3",
        name="Lifetime Energy Consumption L3",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        device_class=SensorDeviceClass.ENERGY,
    ),
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
        name="Relay",
        device_class=BinarySensorDeviceClass.POWER,
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
