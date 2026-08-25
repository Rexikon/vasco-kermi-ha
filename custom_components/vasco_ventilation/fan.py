"""Fan platform for the Vasco Ventilation integration."""

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
    """

    _attr_supported_features = FanEntityFeature.PRESET_MODE
    _attr_name = None

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
        # A heat-recovery ventilation unit is always moving air at one
        # level or another; there is no confirmed "off" write path.
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

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        await self.async_set_preset_mode(preset_mode or _SETTABLE_PRESET_NAMES[0])

    async def async_turn_off(self, **kwargs: Any) -> None:
        raise ServiceValidationError(
            "Turning the unit fully off isn't supported by this integration -- "
            "there is no confirmed wire-protocol write for it. Pick a preset "
            "mode instead."
        )
