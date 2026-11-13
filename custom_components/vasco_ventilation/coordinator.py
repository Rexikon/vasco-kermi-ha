"""DataUpdateCoordinator for the Vasco/Kermi Ventilation integration."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VascoApiClient, ventilation_devices
from .const import (
    DOMAIN,
    MANUAL_DURATION_MINUTES,
    MANUAL_DURATION_PERMANENT,
    MANUAL_DURATION_UNTIL_SCHEDULE,
    MANUAL_PERMANENT,
    MANUAL_UNTIL_NEXT_SCHEDULE,
)
from .exceptions import VascoAuthError, VascoError, VascoNoDevicesError

_LOGGER = logging.getLogger(__name__)

# How long / how often to poll after a write, to reflect the change in the
# UI close to as fast as the official app does (~10s for a real success),
# without hammering the API. Independent of the regular scan_interval.
_CONFIRM_POLL_ATTEMPTS = 6
_CONFIRM_POLL_DELAY = 3


class VascoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls getaccountconfiguration and mediates writes to the unit."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: VascoApiClient,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.client = client
        # Per-device choice of how long a level set from HA holds, kept by
        # the "manual level duration" select (restored across restarts).
        self.manual_duration: dict[str, str] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.async_get_account_configuration()
        except VascoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except VascoError as err:
            raise UpdateFailed(str(err)) from err

    def device_by_serial(self, serial: str) -> dict[str, Any]:
        """Look up a ventilation device in the last-known configuration."""
        for device in ventilation_devices(self.data):
            if device.get("serial") == serial:
                return device
        raise VascoNoDevicesError(f"device {serial!r} not found in account configuration")

    async def async_set_level(self, serial: str, level: int) -> None:
        """Write a new level and poll briefly to reflect it quickly."""
        device = self.device_by_serial(serial)
        await self.client.async_set_level(
            self.data, device, level, self._manual_till(serial)
        )
        await self._async_confirm(
            serial, lambda d: d.get("level") == level, f"level {level}"
        )

    def _manual_till(self, serial: str) -> int:
        """manualSettingActiveTill for a level write, from the chosen duration."""
        option = self.manual_duration.get(serial, MANUAL_DURATION_UNTIL_SCHEDULE)
        if option == MANUAL_DURATION_PERMANENT:
            return MANUAL_PERMANENT
        minutes = MANUAL_DURATION_MINUTES.get(option)
        if not minutes:
            return MANUAL_UNTIL_NEXT_SCHEDULE
        return int((time.time() + minutes * 60) * 1000)

    async def async_write_parameter(
        self,
        serial: str,
        parameter: str,
        value: int,
        confirmed: Callable[[dict[str, Any]], bool],
    ) -> None:
        """Write a raw parameter (e.g. a timed function's minutes) and poll
        briefly until `confirmed(device)` holds."""
        device = self.device_by_serial(serial)
        await self.client.async_write_parameter(self.data, device, parameter, value)
        await self._async_confirm(serial, confirmed, f"{parameter}={value}")

    async def _async_confirm(
        self,
        serial: str,
        confirmed: Callable[[dict[str, Any]], bool],
        what: str,
    ) -> None:
        """Poll briefly after a write to reflect it in the UI quickly.

        This does not raise if the unit never actually applies the write --
        that's a known, unresolved reliability limitation of the underlying
        protocol (see README), not something a HA integration can paper
        over. It logs a warning instead so the failure is visible without
        breaking the service call.
        """
        for attempt in range(_CONFIRM_POLL_ATTEMPTS):
            await asyncio.sleep(_CONFIRM_POLL_DELAY)
            try:
                config = await self.client.async_get_account_configuration()
            except VascoError as err:
                _LOGGER.debug("poll %s/%s after %s failed: %s", attempt + 1, _CONFIRM_POLL_ATTEMPTS, what, err)
                continue
            self.async_set_updated_data(config)
            try:
                if confirmed(self.device_by_serial(serial)):
                    return
            except VascoNoDevicesError:
                return

        _LOGGER.warning(
            "Vasco unit %s did not confirm %s within %ss. "
            "The write was acknowledged by the cloud but the physical unit "
            "may not have applied it -- this is a known intermittent "
            "reliability issue in the vendor's protocol, not necessarily a "
            "bug here. Check the official app.",
            serial,
            what,
            _CONFIRM_POLL_ATTEMPTS * _CONFIRM_POLL_DELAY,
        )
