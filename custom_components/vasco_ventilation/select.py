"""Select platform for the Vasco/Kermi Ventilation integration."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .api import ventilation_devices
from .const import (
    DOMAIN,
    LEVEL_NAMES,
    MANUAL_DURATION_MINUTES,
    MANUAL_DURATION_UNTIL_SCHEDULE,
    MANUAL_PERMANENT,
    NAME_TO_LEVEL,
    SETTABLE_LEVELS,
    WIRE_LEVEL_OFFSET,
)
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
    """Set up the level and manual-duration selects for every device."""
    coordinator: VascoCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SelectEntity] = []
    for device in ventilation_devices(coordinator.data):
        entities.append(VascoLevelSelect(coordinator, device["serial"]))
        entities.append(VascoManualDurationSelect(coordinator, device["serial"]))
    async_add_entities(entities)


def _manual_until(device: dict[str, Any]) -> str | None:
    """How long the current manual level holds: an ISO time, "permanent",
    or None when the schedule is in control (or the deadline has passed --
    the field keeps a stale value after a timed level ends)."""
    till = device.get("manualSettingActiveTill")
    if till == MANUAL_PERMANENT:
        return "permanent"
    if isinstance(till, int) and till > time.time() * 1000:
        return datetime.fromtimestamp(till / 1000, tz=UTC).isoformat()
    return None


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
            "manual_until": _manual_until(device),
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


class VascoManualDurationSelect(VascoEntity, SelectEntity, RestoreEntity):
    """How long a level selected in Home Assistant holds.

    The same choice the official app asks for when a level is picked: until
    the next schedule change, permanently, or for a set time. It only
    affects the next level write; it is not sent to the unit on its own.
    """

    _attr_translation_key = "manual_duration"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:timer-cog-outline"
    _attr_options = list(MANUAL_DURATION_MINUTES)

    def __init__(self, coordinator: VascoCoordinator, serial: str) -> None:
        super().__init__(coordinator, serial)
        self._attr_unique_id = f"{serial}_manual_duration"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in MANUAL_DURATION_MINUTES:
            self.coordinator.manual_duration[self._serial] = last.state

    @property
    def current_option(self) -> str:
        return self.coordinator.manual_duration.get(
            self._serial, MANUAL_DURATION_UNTIL_SCHEDULE
        )

    async def async_select_option(self, option: str) -> None:
        self.coordinator.manual_duration[self._serial] = option
        self.async_write_ha_state()
