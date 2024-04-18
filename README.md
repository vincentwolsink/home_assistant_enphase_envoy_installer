# Enphase Envoy Installer

[![GitHub Release][releases-shield]][releases]
[![Maintainer][maintainer-shield]][maintainer]
[![HACS Custom][hacs-shield]][hacs-url]

This is a HACS custom integration for enphase envoys with firmware version 7 and up.

Especially made to provide extra functionality with your installer or DIY account.
If you want to use the integration with a Home Owner account (with less functionality), select the option during configuration.

Features:
- Individual device per inverter with all information available.
- Individual device per Q-relay with relay status.
- Individual device per battery with information available.
- Production switch to turn on/off solar power production. :one:
- Firmware update sensor.
- 3 Phase CT readings.
- "Realtime" updates of CT readings.
- Configurable polling interval.
- Optional negative production reading correction.
- Service call to retrieve and set grid profile.

:one: Some Enphase installations suffer from an [issue](https://support.enphase.com/s/question/0D53m00009JkKntCAF/when-i-disable-and-later-enable-power-production-through-the-envoy-installer-web-interface-the-microinverters-only-start-producing-power-the-next-morning-instead-of-right-away-why-is-that-and-is-there-any-way-to-make-them-immediately-produce-power) where production only restarts the next morning. This is not an issue with this integration.

## Screenshots

![phase_sensors](https://github.com/vincentwolsink/home_assistant_enphase_envoy_installer/assets/1639734/87fc0c3d-1fd8-4e2c-b7ce-df48531c90e6)
![inverter_sensors](https://github.com/vincentwolsink/home_assistant_enphase_envoy_installer/assets/1639734/d0033e75-6b89-46dd-bf1e-449bbca957f2)

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
