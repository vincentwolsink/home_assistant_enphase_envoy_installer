# Enphase Envoy Installer

[![GitHub Release][releases-shield]][releases]
[![Maintainer][maintainer-shield]][maintainer]
[![HACS Custom][hacs-shield]][hacs-url]

This is a HACS custom integration for enphase envoys with firmware version 7 and up.

Especially made to provide extra functionality with your installer or DIY account.
You can also use the integration with a Home Owner account, without the extra functionality.

Features:
- Individual device per inverter with all information available.
- Individual device per Q-relay with relay status.
- Individual device per battery with information available.
- Production switch to turn on/off solar power production.
- Communication level sensors (optional).
- 3 Phase CT readings.
- "Realtime" updates of CT readings.
- Configurable polling interval.
- Negative production reading correction (optional).
- Service call to retrieve and set and upload grid profile.
- Lifetime production correction (optional).

## Screenshots

![phase_sensors](https://github.com/vincentwolsink/home_assistant_enphase_envoy_installer/assets/1639734/87fc0c3d-1fd8-4e2c-b7ce-df48531c90e6)
<img width=333 src="https://github.com/user-attachments/assets/12da33c1-6be0-40dd-bda1-40e31727eaa5">

## Available Entities
Available entities differ per Envoy type and conf
iguration.

### Envoy
|Entity name|Entity ID|Unit|
|-----------|---------|----|
|Envoy xxx Apparent Power ¹|sensor.envoy_xxx_apparent_power|VA|
|Envoy xxx Apparent Power L1 ¹|sensor.envoy_xxx_apparent_power_l1|VA|
|Envoy xxx Apparent Power L2 ¹|sensor.envoy_xxx_apparent_power_l2|VA|
|Envoy xxx Apparent Power L3 ¹|sensor.envoy_xxx_apparent_power_l3|VA|
|Envoy xxx Batteries Available Energy|sensor.envoy_xxx_batteries_available_energy|Wh|
|Envoy xxx Batteries Capacity|sensor.envoy_xxx_batteries_capacity|Wh|
|Envoy xxx Batteries Charge|sensor.envoy_xxx_batteries_charge|%|
|Envoy xxx Batteries Charge From Grid|switch.envoy_xxx_batteries_charge_from_grid||
|Envoy xxx Batteries Mode|select.envoy_xxx_batteries_mode||
|Envoy xxx Batteries Power|sensor.envoy_xxx_batteries_power|W|
|Envoy xxx Batteries Reserve Charge|number.envoy_xxx_batteries_reserve_charge|%|
|Envoy xxx Batteries Energy Charged|sensor.envoy_xxx_lifetime_batteries_charged|Wh|
|Envoy xxx Batteries Energy Charged L1|sensor.envoy_xxx_lifetime_batteries_charged_l1|Wh|
|Envoy xxx Batteries Energy Charged L2|sensor.envoy_xxx_lifetime_batteries_charged_l2|Wh|
|Envoy xxx Batteries Energy Charged L3|sensor.envoy_xxx_lifetime_batteries_charged_l3|Wh|
|Envoy xxx Batteries Energy Discharged|sensor.envoy_xxx_lifetime_batteries_discharged|Wh|
|Envoy xxx Batteries Energy Discharged L1|sensor.envoy_xxx_lifetime_batteries_discharged_l1|Wh|
|Envoy xxx Batteries Energy Discharged L2|sensor.envoy_xxx_lifetime_batteries_discharged_l2|Wh|
|Envoy xxx Batteries Energy Discharged L3|sensor.envoy_xxx_lifetime_batteries_discharged_l3|Wh|
|Envoy xxx Current Amps ¹|sensor.envoy_xxx_current_amps|A|
|Envoy xxx Current Amps L1 ¹|sensor.envoy_xxx_current_amps_l1|A|
|Envoy xxx Current Amps L2 ¹|sensor.envoy_xxx_current_amps_l2|A|
|Envoy xxx Current Amps L3 ¹|sensor.envoy_xxx_current_amps_l3|A|
|Envoy xxx Current Power Consumption|sensor.envoy_xxx_current_power_consumption|W|
|Envoy xxx Current Power Consumption L1|sensor.envoy_xxx_current_power_consumption_l1|W|
|Envoy xxx Current Power Consumption L2|sensor.envoy_xxx_current_power_consumption_l2|W|
|Envoy xxx Current Power Consumption L3|sensor.envoy_xxx_current_power_consumption_l3|W|
|Envoy xxx Current Power Production|sensor.envoy_xxx_current_power_production|W|
|Envoy xxx Current Power Production L1|sensor.envoy_xxx_current_power_production_l1|W|
|Envoy xxx Current Power Production L2|sensor.envoy_xxx_current_power_production_l2|W|
|Envoy xxx Current Power Production L3|sensor.envoy_xxx_current_power_production_l3|W|
|Envoy xxx Current Voltage|sensor.envoy_xxx_current_voltage|V|
|Envoy xxx Current Voltage L1|sensor.envoy_xxx_current_voltage_l1|V|
|Envoy xxx Current Voltage L2|sensor.envoy_xxx_current_voltage_l2|V|
|Envoy xxx Current Voltage L3|sensor.envoy_xxx_current_voltage_l3|V|
|Envoy xxx Frequency L1 ¹|sensor.envoy_xxx_frequency_l1|Hz|
|Envoy xxx Frequency L2 ¹|sensor.envoy_xxx_frequency_l2|Hz|
|Envoy xxx Frequency L3 ¹|sensor.envoy_xxx_frequency_l3|Hz|
|Envoy xxx Grid Profile|sensor.envoy_xxx_grid_profile||
|Envoy xxx Grid Status|binary_sensor.envoy_xxx_grid_status||
|Envoy xxx Lifetime Energy Consumption|sensor.envoy_xxx_lifetime_energy_consumption|Wh|
|Envoy xxx Lifetime Energy Consumption L1|sensor.envoy_xxx_lifetime_energy_consumption_l1|Wh|
|Envoy xxx Lifetime Energy Consumption L2|sensor.envoy_xxx_lifetime_energy_consumption_l2|Wh|
|Envoy xxx Lifetime Energy Consumption L3|sensor.envoy_xxx_lifetime_energy_consumption_l3|Wh|
|Envoy xxx Lifetime Net Energy Consumption|sensor.envoy_xxx_lifetime_net_energy_consumption|Wh|
|Envoy xxx Lifetime Net Energy Consumption L1|sensor.envoy_xxx_lifetime_net_energy_consumption_l1|Wh|
|Envoy xxx Lifetime Net Energy Consumption L2|sensor.envoy_xxx_lifetime_net_energy_consumption_l2|Wh|
|Envoy xxx Lifetime Net Energy Consumption L3|sensor.envoy_xxx_lifetime_net_energy_consumption_l3|Wh|
|Envoy xxx Lifetime Energy Production|sensor.envoy_xxx_lifetime_energy_production|Wh|
|Envoy xxx Lifetime Energy Production L1|sensor.envoy_xxx_lifetime_energy_production_l1|Wh|
|Envoy xxx Lifetime Energy Production L2|sensor.envoy_xxx_lifetime_energy_production_l2|Wh|
|Envoy xxx Lifetime Energy Production L3|sensor.envoy_xxx_lifetime_energy_production_l3|Wh|
|Envoy xxx Lifetime Net Energy Production|sensor.envoy_xxx_lifetime_energy_production|Wh|
|Envoy xxx Lifetime Net Energy Production L1|sensor.envoy_xxx_lifetime_net_energy_production_l1|Wh|
|Envoy xxx Lifetime Net Energy Production L2|sensor.envoy_xxx_lifetime_net_energy_production_l2|Wh|
|Envoy xxx Lifetime Net Energy Production L3|sensor.envoy_xxx_lifetime_net_energy_production_l3|Wh|
|Envoy xxx Power Factor L1 ¹|sensor.envoy_xxx_power_factor_l1||
|Envoy xxx Power Factor L2 ¹|sensor.envoy_xxx_power_factor_l2||
|Envoy xxx Power Factor L3 ¹|sensor.envoy_xxx_power_factor_l3||
|Envoy xxx Production|switch.envoy_xxx_production||
|Envoy xxx Reactive Power L1 ¹|sensor.envoy_xxx_reactive_power_l1|var|
|Envoy xxx Reactive Power L2 ¹|sensor.envoy_xxx_reactive_power_l2|var|
|Envoy xxx Reactive Power L3 ¹|sensor.envoy_xxx_reactive_power_l3|var|
|Envoy xxx Today's Energy Consumption|sensor.envoy_xxx_today_s_energy_consumption|Wh|
|Envoy xxx Today's Energy Consumption L1|sensor.envoy_xxx_today_s_energy_consumption_l1|Wh|
|Envoy xxx Today's Energy Consumption L2|sensor.envoy_xxx_today_s_energy_consumption_l2|Wh|
|Envoy xxx Today's Energy Consumption L3|sensor.envoy_xxx_today_s_energy_consumption_l3|Wh|
|Envoy xxx Today's Energy Production|sensor.envoy_xxx_today_s_energy_production|Wh|
|Envoy xxx Today's Energy Production L1|sensor.envoy_xxx_today_s_energy_production_l1|Wh|
|Envoy xxx Today's Energy Production L2|sensor.envoy_xxx_today_s_energy_production_l2|Wh|
|Envoy xxx Today's Energy Production L3|sensor.envoy_xxx_today_s_energy_production_l3|Wh|

### Inverter
|Entity name|Entity ID|Unit|
|-----------|---------|----|
|Inverter xxx AC Current|sensor.inverter_xxx_ac_current|A|
|Inverter xxx AC Frequency|sensor.inverter_xxx_ac_frequency|Hz|
|Inverter xxx AC Voltage|sensor.inverter_xxx_ac_voltage|V|
|Inverter xxx Communicating|binary_sensor.inverter_xxx_communicating|
|Inverter xxx Communication Level ¹|sensor.inverter_xxx_communication_level|
|Inverter xxx DC Current|sensor.inverter_xxx_dc_current|A|
|Inverter xxx Last Reading|sensor.inverter_xxx_last_reading||
|Inverter xxx Lifetime Energy Production|sensor.inverter_xxx_lifetime_energy_production|Wh|
|Inverter xxx Power Conversion Error Cycles|sensor.inverter_xxx_power_conversion_error_cycles||
|Inverter xxx Power Conversion Error Seconds|sensor.inverter_xxx_power_conversion_error_seconds|s|
|Inverter xxx Producing|binary_sensor.inverter_xxx_producing||
|Inverter xxx Production|sensor.inverter_xxx_production|W|
|Inverter xxx Temperature|sensor.inverter_xxx_temperature|°C|
|Inverter xxx This Week's Energy Production|sensor.inverter_xxx_this_week_s_energy_production|Wh|
|Inverter xxx Today's Energy Production|sensor.inverter_xxx_today_s_energy_production|Wh|
|Inverter xxx Yesterday's Energy Production|sensor.inverter_xxx_yesterday_s_energy_production|Wh|

### Battery
|Entity name|Entity ID|Unit|
|-----------|---------|----|
|Battery xxx Available Energy|sensor.battery_xxx_available_energy|Wh|
|Battery xxx Capacity|sensor.battery_xxx_capacity|Wh|
|Battery xxx Charge|sensor.battery_xxx_charge|%|
|Battery xxx Communicating|binary_sensor.battery_xxx_communicating||
|Battery xxx DC Switch|binary_sensor.battery_xxx_dc_switch||
|Battery xxx Operating|binary_sensor.battery_xxx_operating||
|Battery xxx Power|sensor.battery_xxx_power|W|
|Battery xxx Sleep|binary_sensor.battery_xxx_sleep||
|Battery xxx Status|sensor.battery_xxx_status||
|Battery xxx Temperature|sensor.battery_xxx_temperature|°C|

### Relay
|Entity name|Entity ID|Unit|
|-----------|---------|----|
|Relay xxx Communicating|binary_sensor.relay_xxx_communicating||
|Relay xxx Communication Level ¹|sensor.relay_xxx_communication_level||
|Relay xxx Contact|binary_sensor.relay_xxx_contact||
|Relay xxx Frequency|binary_sensor.relay_xxx_frequency|Hz|
|Relay xxx Last Reading|sensor.relay_xxx_last_reading||
|Relay xxx State Change Count|sensor.relay_xxx_state_change_count||
|Relay xxx Temperature|sensor.relay_xxx_temperature|°C|
|Relay xxx Voltage L1|sensor.relay_xxx_voltage_l1|V|
|Relay xxx Voltage L2|sensor.relay_xxx_voltage_l2|V|
|Relay xxx Voltage L3|sensor.relay_xxx_voltage_l3|V|

¹ Optional. Enable via integration configuration.

## Installation

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=vincentwolsink&repository=home_assistant_enphase_envoy_installer&category=integration)

Or follow these steps:
1. Install [HACS](https://hacs.xyz/) if you haven't already
2. Add this repository as a [custom integration repository](https://hacs.xyz/docs/faq/custom_repositories) in HACS
4. Restart home assistant
5. Add the integration through the home assistant configuration flow

## Credits
Based on work from [@briancmpbll](https://github.com/briancmpbll/home_assistant_custom_envoy)

[releases-shield]: https://img.shields.io/github/v/release/vincentwolsink/home_assistant_enphase_envoy_installer.svg?style=for-the-badge
[releases]: https://github.com/vincentwolsink/home_assistant_enphase_envoy_installer/releases
[maintainer-shield]: https://img.shields.io/badge/maintainer-vincentwolsink-blue.svg?style=for-the-badge
[maintainer]: https://github.com/vincentwolsink
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge
[hacs-url]: https://github.com/vincentwolsink/home_assistant_enphase_envoy_installer
