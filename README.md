# Enphase Envoy Installer

[![GitHub Release][releases-shield]][releases]
[![Maintainer][maintainer-shield]][maintainer]
[![HACS Custom][hacs-shield]][hacs-url]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]

This is a HACS custom integration for enphase envoys with firmware version 7.X. To be used with your installer account.

Features:
- Individual device per inverter with all information available. 
- Individual device per Q-relay with relay status.
- "Production" switch to turn on/off solar power production.
- Firmware update sensor.
- 3 Phase CT readings.

Based on work from [@briancmpbll](https://github.com/briancmpbll/home_assistant_custom_envoy) and [@posixx](https://github.com/posixx/home_assistant_custom_envoy)


# Installation

1. Install [HACS](https://hacs.xyz/) if you haven't already
2. Add this repository as a [custom integration repository](https://hacs.xyz/docs/faq/custom_repositories) in HACS
4. Restart home assistant
5. Add the integration through the home assistant configuration flow

[releases-shield]: https://img.shields.io/github/v/release/vincentwolsink/home_assistant_enphase_envoy_installer.svg?style=for-the-badge
[releases]: https://github.com/vincentwolsink/home_assistant_enphase_envoy_installer/releases
[maintainer-shield]: https://img.shields.io/badge/maintainer-vincentwolsink-blue.svg?style=for-the-badge
[maintainer]: https://github.com/vincentwolsink
[buymecoffee]: https://ko-fi.com/vincentwolsink
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-tip-yellow.svg?style=for-the-badge
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge
[hacs-url]: https://github.com/vincentwolsink/home_assistant_enphase_envoy_installer
