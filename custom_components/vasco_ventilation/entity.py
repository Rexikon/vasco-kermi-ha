"""Base entity for the Vasco/Kermi Ventilation integration."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import VascoCoordinator
from .exceptions import VascoNoDevicesError


class VascoEntity(CoordinatorEntity[VascoCoordinator]):
    """Base entity tied to a single ventilation device, by serial."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VascoCoordinator, serial: str) -> None:
        super().__init__(coordinator)
        self._serial = serial
        device = coordinator.device_by_serial(serial)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=device.get("name") or serial,
            manufacturer=MANUFACTURER,
            model=device.get("productTypeString"),
            sw_version=(
                str(device["swVersion"]) if device.get("swVersion") is not None else None
            ),
        )

    @property
    def device(self) -> dict[str, Any]:
        """Current device-properties dict from the coordinator's last poll."""
        return self.coordinator.device_by_serial(self._serial)

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        try:
            self.coordinator.device_by_serial(self._serial)
        except VascoNoDevicesError:
            return False
        return True
