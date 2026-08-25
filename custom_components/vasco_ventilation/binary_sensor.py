"""Binary sensor platform for the Vasco/Kermi Ventilation integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ventilation_devices
from .const import DOMAIN
from .coordinator import VascoCoordinator
from .entity import VascoEntity


@dataclass(frozen=True, kw_only=True)
class VascoBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a Vasco binary sensor and how to read it off a device dict."""

    is_on_fn: Callable[[dict[str, Any]], bool]


BINARY_SENSOR_DESCRIPTIONS: tuple[VascoBinarySensorDescription, ...] = (
    # No PROBLEM device_class: that forces HA's "OK"/"Problem" labels.
    # Custom off/on translations render as Brak/Tak (None/Yes) instead.
    VascoBinarySensorDescription(
        key="filter_dirty",
        translation_key="filter_dirty",
        icon="mdi:air-filter",
        is_on_fn=lambda d: bool(d.get("filterDirty")),
    ),
    VascoBinarySensorDescription(
        key="fault",
        translation_key="fault",
        icon="mdi:alert-circle-outline",
        is_on_fn=lambda d: bool(d.get("faultStatus")),
    ),
    VascoBinarySensorDescription(
        key="defrost",
        translation_key="defrost",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:snowflake-melt",
        is_on_fn=lambda d: bool(d.get("defrost")),
    ),
    # Read-only: the write path for fireplace boost hasn't been verified
    # against real device traffic, so this integration doesn't offer a
    # switch for it (see README's Known limitations) -- but reading the
    # official app's own state back is safe and useful.
    VascoBinarySensorDescription(
        key="fireplace_boost_active",
        translation_key="fireplace_boost_active",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:fireplace",
        is_on_fn=lambda d: bool(d.get("fireplaceModeStatus")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up binary sensors for every ventilation device on the account."""
    coordinator: VascoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        VascoBinarySensor(coordinator, device["serial"], description)
        for device in ventilation_devices(coordinator.data)
        for description in BINARY_SENSOR_DESCRIPTIONS
    )


class VascoBinarySensor(VascoEntity, BinarySensorEntity):
    """A single read-only flag off a Vasco ventilation device."""

    entity_description: VascoBinarySensorDescription

    def __init__(
        self,
        coordinator: VascoCoordinator,
        serial: str,
        description: VascoBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator, serial)
        self.entity_description = description
        self._attr_unique_id = f"{serial}_{description.key}"

    @property
    def is_on(self) -> bool:
        return self.entity_description.is_on_fn(self.device)
