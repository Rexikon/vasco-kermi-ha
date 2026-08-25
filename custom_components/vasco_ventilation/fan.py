"""Fan platform for the Vasco/Kermi Ventilation integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ventilation_devices
from .const import DOMAIN, LEVEL_NAMES, NAME_TO_LEVEL, SETTABLE_LEVELS
from .coordinator import VascoCoordinator
from .entity import VascoEntity

_LOGGER = logging.getLogger(__name__)

_SETTABLE_PRESET_NAMES = [LEVEL_NAMES[level] for level in SETTABLE_LEVELS]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up one fan entity per ventilation device found on the account."""
    coordinator: VascoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        VascoFan(coordinator, device["serial"])
        for device in ventilation_devices(coordinator.data)
    )


class VascoFan(VascoEntity, FanEntity):
    """A Vasco ventilation unit, exposed as a preset-mode fan.

    The vendor API is level-based (Low/Medium/High/Auto/...), not a
    continuous percentage, so this uses preset_mode rather than
    percentage/speed_count -- matching how the official app presents it.

    There is no confirmed off command, so TURN_ON/TURN_OFF are intentionally
    omitted: the UI shows status + preset modes only.
    """

    _attr_supported_features = FanEntityFeature.PRESET_MODE
    _attr_name = None
    # Without this, HA would auto-add TURN_ON/TURN_OFF because older fans
    # implied those from method presence -- we deliberately do not support them.
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: VascoCoordinator, serial: str) -> None:
        super().__init__(coordinator, serial)
        self._attr_unique_id = serial

    @property
    def preset_modes(self) -> list[str]:
        return _SETTABLE_PRESET_NAMES

    @property
    def preset_mode(self) -> str | None:
        # May legitimately fall outside preset_modes -- e.g. the unit was
        # put into Auto from the official app. Still shown for visibility;
        # only *setting* it is restricted to the confirmed levels.
        return LEVEL_NAMES.get(self.device.get("level"))

    @property
    def is_on(self) -> bool:
        # Always running at some level; no off write path exists.
        return True

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        device = self.device
        return {
            "control_mode": device.get("controlMode"),
            "next_scheduled_level": LEVEL_NAMES.get(device.get("nextValue")),
        }

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        level = NAME_TO_LEVEL.get(preset_mode)
        if level is None or level not in SETTABLE_LEVELS:
            raise ServiceValidationError(
                f"'{preset_mode}' is not a settable preset on this integration "
                f"(supported: {', '.join(_SETTABLE_PRESET_NAMES)}). Its wire-protocol "
                "encoding hasn't been confirmed against real device traffic -- "
                "see the README's Known limitations."
            )
        await self.coordinator.async_set_level(self._serial, level)
