"""Button platform for the Vasco/Kermi Ventilation integration.

The official app starts its timed functions by writing the duration in
minutes to a parameter; the unit runs the function and ends it itself.
Both buttons write the duration the unit currently holds: for Boost that
is its configured boost time (the app never asks), for Fireplace mode the
time last picked in the app.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ventilation_devices
from .const import (
    DEFAULT_BOOST_MINUTES,
    DEFAULT_FIREPLACE_MINUTES,
    DOMAIN,
    LEVEL_BOOST,
    PARAM_BOOST_MINUTES,
    PARAM_FIREPLACE_MINUTES,
)
from .coordinator import VascoCoordinator
from .entity import VascoEntity


@dataclass(frozen=True, kw_only=True)
class VascoButtonDescription(ButtonEntityDescription):
    """A timed function started by writing its duration in minutes."""

    parameter: str
    default_minutes: int
    confirmed: Callable[[dict[str, Any]], bool]


BUTTON_DESCRIPTIONS: tuple[VascoButtonDescription, ...] = (
    # The app's "Regulator": High at boost speed (94-95 % on an X425) for
    # overrideTimeSpeed3 minutes; the unit reports level 13 meanwhile.
    VascoButtonDescription(
        key="boost",
        translation_key="boost",
        icon="mdi:fan-plus",
        parameter=PARAM_BOOST_MINUTES,
        default_minutes=DEFAULT_BOOST_MINUTES,
        confirmed=lambda d: d.get("level") == LEVEL_BOOST,
    ),
    # Fireplace mode: limits extract below supply (overpressure) so a
    # fireplace draws properly. Runs alongside the level, which can still
    # be changed; the unit clears fireplaceModeStatus when the time is up.
    VascoButtonDescription(
        key="fireplace",
        translation_key="fireplace",
        icon="mdi:fireplace",
        parameter=PARAM_FIREPLACE_MINUTES,
        default_minutes=DEFAULT_FIREPLACE_MINUTES,
        confirmed=lambda d: bool(d.get("fireplaceModeStatus")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the timed-function buttons for every ventilation device."""
    coordinator: VascoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        VascoButton(coordinator, device["serial"], description)
        for device in ventilation_devices(coordinator.data)
        for description in BUTTON_DESCRIPTIONS
    )


class VascoButton(VascoEntity, ButtonEntity):
    """Starts a timed function on the unit."""

    entity_description: VascoButtonDescription

    def __init__(
        self,
        coordinator: VascoCoordinator,
        serial: str,
        description: VascoButtonDescription,
    ) -> None:
        super().__init__(coordinator, serial)
        self.entity_description = description
        self._attr_unique_id = f"{serial}_{description.key}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"duration_minutes": self._minutes()}

    def _minutes(self) -> int:
        value = self.device.get(self.entity_description.parameter)
        return value if isinstance(value, int) and value > 0 else self.entity_description.default_minutes

    async def async_press(self) -> None:
        description = self.entity_description
        await self.coordinator.async_write_parameter(
            self._serial, description.parameter, self._minutes(), description.confirmed
        )
