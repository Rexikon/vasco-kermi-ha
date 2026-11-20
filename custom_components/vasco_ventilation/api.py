"""Async client for the Vasco iqloud cloud API.

Protocol notes (learned the hard way, see the project README):

- Every REST call is POST https://vasco.iqloud.eu/api/<functionName> with a
  JSON body whose "payload" value is itself a JSON-encoded *string*, not a
  nested object -- sending a raw object there fails with
  errorCode "JSON PAYLOAD FAILED".
- REST's `setdeviceproperties` only updates the cloud's bookkeeping. It does
  **not** push a ventilation level change to the physical unit. That only
  happens over the bridge's WebSocket (`writeData`), which is why
  async_set_level below exists as a separate code path from the plain REST
  device-properties update used for polling.
- The WebSocket write's `requestedLevel` value is NOT the same integer as
  the cloud/account API's `requestedLevel` enum -- see WIRE_LEVEL_OFFSET in
  const.py.
- WebSocket frames must be sent as *binary* (opcode 0x2). Text frames are
  silently ignored by the server.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from .const import (
    API_BASE,
    MANUAL_UNTIL_NEXT_SCHEDULE,
    PRODUCT_CATEGORY_VENTILATION,
    USER_AGENT,
    WIRE_LEVEL_OFFSET,
)
from .exceptions import (
    VascoApiError,
    VascoAuthError,
    VascoBridgeRejectedError,
    VascoConnectionError,
)

_LOGGER = logging.getLogger(__name__)

_HEADERS = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
_WS_TIMEOUT = 15


def ventilation_devices(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the VENTILATION-category devices in an account configuration."""
    return [
        device
        for device in config.get("deviceProperties", [])
        if device.get("productCategory") == PRODUCT_CATEGORY_VENTILATION
    ]


def find_bridge(config: dict[str, Any], device: dict[str, Any]) -> dict[str, Any]:
    """Find the bridge that owns a device."""
    for bridge in config.get("bridges", []):
        if bridge.get("macAddress") == device.get("macAddress"):
            return bridge
    bridges = config.get("bridges", [])
    if len(bridges) == 1:
        return bridges[0]
    raise VascoConnectionError(f"could not find the bridge for device {device.get('serial')!r}")


class VascoApiClient:
    """Thin async wrapper around the Vasco iqloud REST + WebSocket API."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._token: str | None = None

    @property
    def token(self) -> str | None:
        return self._token

    async def async_login(self) -> str:
        """Log in and cache the userToken. Raises VascoAuthError on bad
        credentials, VascoConnectionError on network failure."""
        # Bad credentials come back as errorCode "FAILED" with extraInfo
        # "LOGIN_FAILED"; _api_post classifies that as VascoAuthError. Any
        # other failure (server error, rate limit) stays a VascoApiError so
        # a vendor outage doesn't ask the user to re-enter a valid password.
        payload = await self._api_post(
            "login",
            {"userInfo": {"email": self._email, "password": self._password}},
            authed=False,
        )
        if not isinstance(payload, dict) or not payload.get("userToken"):
            raise VascoAuthError("login succeeded but no userToken was returned")
        self._token = payload["userToken"]
        return self._token

    async def async_get_account_configuration(self) -> dict[str, Any]:
        """Fetch rooms, device properties, bridges, schedule -- everything."""
        config = await self._api_post("getaccountconfiguration", {})
        if not isinstance(config, dict):
            raise VascoApiError("getaccountconfiguration returned an unexpected payload")
        return config

    async def async_set_device_properties(self, device: dict[str, Any]) -> None:
        """REST bookkeeping update. Full object only, never a delta -- a
        partial object here has been observed to corrupt the account's
        stored device state (duplicate entry, sensor fields wiped to null).
        Does NOT push a level change to the physical unit; see
        async_set_level for that."""
        await self._api_post("setdeviceproperties", [device])

    async def async_set_level(
        self,
        config: dict[str, Any],
        device: dict[str, Any],
        level: int,
        manual_till: int = MANUAL_UNTIL_NEXT_SCHEDULE,
    ) -> None:
        """Write a ventilation level to the unit over the bridge WebSocket.

        manual_till is how long the level holds, the same choice the
        official app offers: MANUAL_UNTIL_NEXT_SCHEDULE (0), MANUAL_PERMANENT
        (-1), or an end time in epoch milliseconds. It must always be sent
        explicitly: the field keeps its old value after a boost or a timed
        level has ended, and echoing that back makes the new level end at
        the old deadline.
        """
        await self.async_write_parameter(
            config,
            {**device, "manualSettingActiveTill": manual_till},
            "requestedLevel",
            WIRE_LEVEL_OFFSET.get(level, level),
        )

    async def async_write_parameter(
        self, config: dict[str, Any], device: dict[str, Any], parameter: str, value: int
    ) -> None:
        """Write one raw parameter to the unit over the bridge WebSocket.

        This sends the ack-worthy command and returns once the bridge has
        acknowledged the write (or after a short timeout if it never does).
        It intentionally does NOT poll/confirm the physical state changed --
        that's the coordinator's job, since the only trustworthy source of
        truth is a fresh REST read, never the WS ack alone.
        """
        if self._token is None:
            await self.async_login()
        try:
            await self._ws_write(config, device, parameter, value)
        except VascoBridgeRejectedError:
            # Most likely an expired userToken: REST only refreshes it when
            # a poll fails, so a write can get there first. Retry once.
            _LOGGER.debug("bridge rejected the connection; logging in again")
            self._token = None
            await self.async_login()
            await self._ws_write(config, device, parameter, value)

    async def _ws_write(
        self, config: dict[str, Any], device: dict[str, Any], parameter: str, value: int
    ) -> None:
        bridge = find_bridge(config, device)
        url = bridge["appServerURL"].replace("ws://", "wss://")
        params = {"bridgeToken": bridge["bridgeToken"], "userToken": self._token}

        # Round-trip the device object as received (apart from
        # manualSettingActiveTill, set by async_set_level like the app
        # does). Forcing controlMode to "manual" (an earlier, wrong
        # assumption) actively broke writes.
        account_properties_changed = json.dumps(
            {
                "functionName": "accountPropertiesChanged",
                "itemName": "deviceProperties",
                "mustSyncOtherApps": True,
                "payload": json.dumps([device]),
            }
        )
        write_data = json.dumps(
            {
                "functionName": "writeData",
                "parameterName": parameter,
                "data": value,
                "modbusAddress": device["modbusAddress"],
                "swVersion": device["swVersion"],
                "productType": device["productType"],
            }
        )

        try:
            async with asyncio.timeout(_WS_TIMEOUT):
                async with self._session.ws_connect(url, params=params) as ws:
                    ready = False
                    async for msg in ws:
                        frame = _decode_ws_json(msg)
                        if frame is None:
                            continue
                        if frame.get("functionName") == "connectionStatus":
                            if frame.get("status") != "OK":
                                raise VascoBridgeRejectedError(
                                    "bridge rejected the WebSocket connection: "
                                    f"{frame.get('status')}"
                                )
                            ready = True
                            break
                    if not ready:
                        raise VascoConnectionError(
                            "bridge closed the WebSocket before it was ready"
                        )

                    await ws.send_bytes(account_properties_changed.encode())
                    await ws.send_bytes(write_data.encode())

                    async for msg in ws:
                        frame = _decode_ws_json(msg)
                        if frame is None:
                            continue
                        if (
                            frame.get("functionName") == "dataWritten"
                            and frame.get("parameterName") == parameter
                        ):
                            return
        except TimeoutError:
            # Not fatal -- the bridge sometimes doesn't send a timely ack
            # even on a real, successful app write. The caller re-polls
            # REST afterwards to find out what actually happened.
            _LOGGER.debug("no dataWritten ack within %ss for %s=%s", _WS_TIMEOUT, parameter, value)
        except (aiohttp.ClientError, OSError) as err:
            # OSError covers ConnectionResetError from sending on a socket
            # the bridge has already closed.
            raise VascoConnectionError(f"WebSocket write failed: {err}") from err

    async def _api_post(
        self,
        function_name: str,
        inner_payload: Any = None,
        authed: bool = True,
        _retried: bool = False,
    ) -> Any:
        body: dict[str, Any] = {}
        if inner_payload is not None:
            body["payload"] = json.dumps(inner_payload)
        if authed:
            if self._token is None:
                await self.async_login()
            body["userToken"] = self._token

        try:
            async with self._session.post(
                f"{API_BASE}/{function_name}",
                json=body,
                headers=_HEADERS,
                timeout=_REQUEST_TIMEOUT,
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except (ValueError, aiohttp.ContentTypeError) as err:
                    raise VascoConnectionError(
                        f"{function_name} returned non-JSON (HTTP {resp.status})"
                    ) from err
        except (aiohttp.ClientError, TimeoutError) as err:
            raise VascoConnectionError(f"network error calling {function_name}: {err}") from err

        if not isinstance(data, dict) or data.get("status") != "success":
            payload = data.get("payload") if isinstance(data, dict) else None
            if not isinstance(payload, dict):
                payload = {}
            error_code = str(
                payload.get("errorCode")
                or (data.get("status") if isinstance(data, dict) else None)
                or "unknown"
            )
            if payload.get("extraInfo"):
                error_code = f"{error_code}/{payload['extraInfo']}"
            is_auth_error = _is_auth_error(error_code)
            if authed and is_auth_error and not _retried:
                _LOGGER.debug("re-authenticating after %s from %s", error_code, function_name)
                self._token = None
                return await self._api_post(
                    function_name, inner_payload, authed=authed, _retried=True
                )
            if is_auth_error:
                raise VascoAuthError(f"{function_name} failed: {error_code}")
            raise VascoApiError(f"{function_name} failed: {error_code}")

        return data.get("payload")


def _is_auth_error(error_code: str) -> bool:
    """Whether an API error code means the credentials or token were rejected.

    Bad credentials: errorCode "FAILED", extraInfo "LOGIN_FAILED". A rate
    limit ("too many login attempts") is transient, not an auth failure.
    """
    code = error_code.upper()
    if "TOO_MANY" in code:
        return False
    return any(kw in code for kw in ("LOGIN", "TOKEN", "AUTH", "NOT_VERIFIED"))


def _decode_ws_json(msg: aiohttp.WSMessage) -> dict[str, Any] | None:
    if msg.type not in (aiohttp.WSMsgType.TEXT, aiohttp.WSMsgType.BINARY):
        return None
    try:
        data = json.loads(msg.data)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None
