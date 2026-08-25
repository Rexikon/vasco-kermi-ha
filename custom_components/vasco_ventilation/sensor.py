"""Sensor platform for the Vasco/Kermi Ventilation integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EntityCategory,
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolumeFlowRate,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import ventilation_devices
from .const import DOMAIN
from .coordinator import VascoCoordinator
from .entity import VascoEntity


@dataclass(frozen=True, kw_only=True)
class VascoSensorDescription(SensorEntityDescription):
    """Describes a Vasco sensor and how to read it off a device dict."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSOR_DESCRIPTIONS: tuple[VascoSensorDescription, ...] = (
    VascoSensorDescription(
        key="indoor_temperature",
        translation_key="indoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("indoorTemperature"),
    ),
    VascoSensorDescription(
        key="outdoor_temperature",
        translation_key="outdoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("outdoorTemperature"),
    ),
    VascoSensorDescription(
        key="supply_temperature",
        translation_key="supply_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("supplyTemperature"),
    ),
    VascoSensorDescription(
        key="exhaust_temperature",
        translation_key="exhaust_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("exhaustTemperature"),
    ),
    VascoSensorDescription(
        key="inlet_flow",
        translation_key="inlet_flow",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:home-import-outline",
        value_fn=lambda d: d.get("actualInletFlow"),
    ),
    VascoSensorDescription(
        key="exhaust_flow",
        translation_key="exhaust_flow",
        device_class=SensorDeviceClass.VOLUME_FLOW_RATE,
        native_unit_of_measurement=UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:home-export-outline",
        value_fn=lambda d: d.get("actualExhaustFlow"),
    ),
    VascoSensorDescription(
        key="inlet_fan_speed",
        translation_key="inlet_fan_speed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:fan-plus",
        value_fn=lambda d: d.get("actualFanSpeedInlet"),
    ),
    VascoSensorDescription(
        key="exhaust_fan_speed",
        translation_key="exhaust_fan_speed",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:fan-minus",
        value_fn=lambda d: d.get("actualFanSpeedExhaust"),
    ),
    VascoSensorDescription(
        key="bypass_position",
        translation_key="bypass_position",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:valve",
        value_fn=lambda d: d.get("bypassPosition"),
    ),
    # Per the protocol notes: this looks like the *configured* replace
    # interval, not a live countdown -- named accordingly so it doesn't
    # imply an ETA the API doesn't actually provide.
    VascoSensorDescription(
        key="filter_replace_interval",
        translation_key="filter_replace_interval",
        native_unit_of_measurement=UnitOfTime.DAYS,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:calendar-clock",
        value_fn=lambda d: d.get("filterReplaceTime"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up sensors for every ventilation device on the account."""
    coordinator: VascoCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        VascoSensor(coordinator, device["serial"], description)
        for device in ventilation_devices(coordinator.data)
        for description in SENSOR_DESCRIPTIONS
    )


class VascoSensor(VascoEntity, SensorEntity):
    """A single read-only measurement off a Vasco ventilation device."""

    entity_description: VascoSensorDescription

    def __init__(
        self,
        coordinator: VascoCoordinator,
        serial: str,
        description: VascoSensorDescription,
    ) -> None:
        super().__init__(coordinator, serial)
        self.entity_description = description
        self._attr_unique_id = f"{serial}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.device)
