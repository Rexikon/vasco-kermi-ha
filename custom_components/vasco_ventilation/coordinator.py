"""DataUpdateCoordinator for the Vasco/Kermi Ventilation integration."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VascoApiClient, find_bridge, ventilation_devices
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

type VascoConfigEntry = ConfigEntry[VascoCoordinator]

# How long / how often to poll after a write, to reflect the change in the
# UI close to as fast as the official app does (~10s for a real success),
# without hammering the API. Independent of the regular scan_interval.
_CONFIRM_POLL_ATTEMPTS = 6
_CONFIRM_POLL_DELAY = 3

# Reconnect backoff for the live-updates connection, in seconds. A
# connection that stayed up for _LIVE_STABLE resets it to the minimum.
_LIVE_BACKOFF_MIN = 5
_LIVE_BACKOFF_MAX = 300
_LIVE_STABLE = 60


def apply_value_changed(data: dict[str, Any], frame: dict[str, Any]) -> dict[str, Any] | None:
    """Apply a bridge `valueChanged` frame to an account configuration.

    The frame names a deviceProperties entry by its index in the account's
    deviceProperties list, e.g.
    {"functionName": "valueChanged", "itemName": "deviceProperties",
     "index": 0, "parameterName": "actualFanSpeedInlet", "value": 70}.
    Returns the updated configuration (new dicts, the input is untouched),
    or None when the frame is something else or changes nothing.
    """
    if frame.get("functionName") != "valueChanged" or frame.get("itemName") != "deviceProperties":
        return None
    index = frame.get("index")
    parameter = frame.get("parameterName")
    devices = data.get("deviceProperties")
    if (
        not isinstance(index, int)
        or not isinstance(parameter, str)
        or not isinstance(devices, list)
        or not 0 <= index < len(devices)
    ):
        return None
    device = devices[index]
    value = frame.get("value")
    if parameter in device and device[parameter] == value:
        return None
    new_devices = list(devices)
    new_devices[index] = {**device, parameter: value}
    return {**data, "deviceProperties": new_devices}


class VascoCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls getaccountconfiguration and mediates writes to the unit."""

    config_entry: VascoConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: VascoConfigEntry,
        client: VascoApiClient,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.client = client
        # Per-device choice of how long a level set from HA holds, kept by
        # the "manual level duration" select (restored across restarts).
        self.manual_duration: dict[str, str] = {}
        # Serials whose bridge connection for live updates is currently up.
        self.live_connected: set[str] = set()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.async_get_account_configuration()
        except VascoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except VascoError as err:
            raise UpdateFailed(str(err)) from err

    @callback
    def async_start_live_updates(self) -> None:
        """Listen on each bridge's WebSocket and apply the pushed changes.

        Changes then show up within a second or two, including ones made
        from the official app or the RF remote, instead of on the next poll.
        Regular polling keeps running as a fallback and to pick up fields the
        bridge doesn't push. One connection per bridge; the tasks end when the
        config entry is unloaded.
        """
        listeners: dict[str, str] = {}
        for device in ventilation_devices(self.data):
            try:
                bridge = find_bridge(self.data, device)
            except VascoError as err:
                _LOGGER.debug("no live updates for %s: %s", device.get("serial"), err)
                continue
            listeners.setdefault(str(bridge.get("bridgeToken")), device["serial"])
        for serial in listeners.values():
            self.config_entry.async_create_background_task(
                self.hass, self._async_live_loop(serial), f"{DOMAIN} live updates {serial}"
            )

    async def _async_live_loop(self, serial: str) -> None:
        """Keep the live-updates connection up, reconnecting with backoff."""
        backoff = _LIVE_BACKOFF_MIN
        while True:
            started = time.monotonic()
            try:
                device = self.device_by_serial(serial)
                await self.client.async_listen(
                    self.data,
                    device,
                    self._async_handle_frame,
                    lambda: self._async_live_connected(serial),
                )
                reason = "closed by the server"
            except VascoAuthError as err:
                # Polling raises reauth for bad credentials; don't hammer
                # the login endpoint from here meanwhile.
                reason = str(err)
                backoff = _LIVE_BACKOFF_MAX
            except VascoError as err:
                reason = str(err)
            self.live_connected.discard(serial)
            if time.monotonic() - started >= _LIVE_STABLE:
                backoff = _LIVE_BACKOFF_MIN
            _LOGGER.debug(
                "live updates for %s disconnected after %.0fs (%s); reconnecting in %ss",
                serial,
                time.monotonic() - started,
                reason,
                backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _LIVE_BACKOFF_MAX)

    @callback
    def _async_live_connected(self, serial: str) -> None:
        _LOGGER.debug("live updates for %s connected", serial)
        self.live_connected.add(serial)

    @callback
    def _async_handle_frame(self, frame: dict[str, Any]) -> None:
        """Apply one pushed frame and notify the entities.

        Sets data directly instead of async_set_updated_data(): that would
        reschedule the next poll on every frame, and frames arrive often
        enough (temperatures) that polling would never run.
        """
        if self.data is None:
            return
        updated = apply_value_changed(self.data, frame)
        if updated is None:
            return
        self.data = updated
        self.async_update_listeners()

    def device_by_serial(self, serial: str) -> dict[str, Any]:
        """Look up a ventilation device in the last-known configuration."""
        for device in ventilation_devices(self.data):
            if device.get("serial") == serial:
                return device
        raise VascoNoDevicesError(f"device {serial!r} not found in account configuration")

    async def async_set_level(self, serial: str, level: int) -> None:
        """Write a new level and poll briefly to reflect it quickly."""
        device = self.device_by_serial(serial)
        await self._async_write(
            self.client.async_set_level(self.data, device, level, self._manual_till(serial))
        )
        await self._async_confirm(serial, lambda d: d.get("level") == level, f"level {level}")

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
        await self._async_write(
            self.client.async_write_parameter(self.data, device, parameter, value)
        )
        await self._async_confirm(serial, confirmed, f"{parameter}={value}")

    async def _async_write(self, write: Awaitable[None]) -> None:
        """Run a write, turning API errors into a readable HA error.

        Without this a network or auth problem surfaces as an unexpected
        exception with a stack trace instead of a message in the UI.
        """
        try:
            await write
        except VascoAuthError as err:
            self.config_entry.async_start_reauth(self.hass)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="auth_failed",
            ) from err
        except VascoError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err

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
                _LOGGER.debug(
                    "poll %s/%s after %s failed: %s", attempt + 1, _CONFIRM_POLL_ATTEMPTS, what, err
                )
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
