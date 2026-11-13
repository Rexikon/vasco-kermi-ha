"""Select platform for the Vasco/Kermi Ventilation integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ventilation_devices
from .const import DOMAIN, LEVEL_NAMES, NAME_TO_LEVEL, SETTABLE_LEVELS, WIRE_LEVEL_OFFSET
from .coordinator import VascoCoordinator
from .entity import VascoEntity

_LOGGER = logging.getLogger(__name__)

_SETTABLE_LEVEL_NAMES = [LEVEL_NAMES[level] for level in SETTABLE_LEVELS]

# nextValue (like homeModes[].devices[].value) uses the wire encoding
# (2/3/4 = Low/Medium/High), not the cloud level enum.
_WIRE_TO_LEVEL = {wire: level for level, wire in WIRE_LEVEL_OFFSET.items()}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up one ventilation-level select entity per device found on the account."""
    coordinator: VascoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        VascoLevelSelect(coordinator, device["serial"])
        for device in ventilation_devices(coordinator.data)
    )


class VascoLevelSelect(VascoEntity, SelectEntity):
    """The ventilation level, exposed as a select rather than a fan toggle.

    The unit has no confirmed off command and is always running at some
    level, so a fan entity misrepresents it -- Home Assistant renders a
    fan's entity row with an on/off toggle the device can't act on. A
    select has no on/off notion, its state (the level itself) is tracked in
    history like any other entity -- unlike a fan's preset_mode, which is
    only an attribute -- and its dropdown appears directly in entity rows
    instead of behind the more-info dialog.

    All known levels are listed as options so the current one is always a
    valid state. Boost (the app's timed "Regulator") is shown but not
    selectable here: it is started with its own button and ends itself, or
    when another level is selected. See SETTABLE_LEVELS in const.py.
    """

    _attr_name = None
    _attr_options = list(LEVEL_NAMES.values())

    def __init__(self, coordinator: VascoCoordinator, serial: str) -> None:
        super().__init__(coordinator, serial)
        self._attr_unique_id = serial

    @property
    def current_option(self) -> str | None:
        return LEVEL_NAMES.get(self.device.get("level"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        device = self.device
        return {
            "control_mode": device.get("controlMode"),
            "next_scheduled_level": LEVEL_NAMES.get(_WIRE_TO_LEVEL.get(device.get("nextValue"))),
        }

    async def async_select_option(self, option: str) -> None:
        level = NAME_TO_LEVEL.get(option)
        if level is None or level not in SETTABLE_LEVELS:
            raise ServiceValidationError(
                f"'{option}' can't be selected here "
                f"(supported: {', '.join(_SETTABLE_LEVEL_NAMES)}). "
                "Use the Boost button to start a timed boost."
            )
        await self.coordinator.async_set_level(self._serial, level)
