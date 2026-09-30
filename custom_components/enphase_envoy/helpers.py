"""Helpers for the Enphase Envoy integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

# HA Core 2026.8 deprecated `via_device` in favour of `via_device_id`, which
# takes a device id instead of an identifier tuple. Older versions reject
# `via_device_id` as an invalid device info key, so keep using `via_device`
# there. The registry lookup used to resolve the device id was added in the
# same release, so its presence is used to detect support.
_SUPPORTS_VIA_DEVICE_ID = hasattr(dr.DeviceRegistry, "async_get_device_by_identifier")


def via_device_kw(hass: HomeAssistant, config_entry: ConfigEntry) -> dict[str, Any]:
    """Return the device info key that links a device to the Envoy device."""
    if not config_entry.unique_id:
        return {}

    if not _SUPPORTS_VIA_DEVICE_ID:
        return {"via_device": (DOMAIN, config_entry.unique_id)}

    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, config_entry.unique_id), config_entry.entry_id
    )
    if device is None:
        return {}
    return {"via_device_id": device.id}
