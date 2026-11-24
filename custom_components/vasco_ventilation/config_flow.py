"""Config flow for the Vasco/Kermi Ventilation integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VascoApiClient, ventilation_devices
from .const import (
    CONF_LIVE_UPDATES,
    CONF_SCAN_INTERVAL_SECONDS,
    DEFAULT_LIVE_UPDATES,
    DOMAIN,
)
from .exceptions import VascoApiError, VascoAuthError, VascoConnectionError

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class NoDevicesFound(Exception):
    """Raised when the account has no ventilation device to add."""


async def _validate_and_get_unique_id(hass: Any, data: dict[str, Any]) -> str:
    """Log in and confirm at least one ventilation device exists.

    Returns the (lowercased) account email, used as the config entry's
    unique_id so the same account can't be added twice.
    """
    session = async_get_clientsession(hass)
    client = VascoApiClient(session, data[CONF_EMAIL], data[CONF_PASSWORD])
    await client.async_login()
    config = await client.async_get_account_configuration()
    if not ventilation_devices(config):
        raise NoDevicesFound
    return data[CONF_EMAIL].strip().lower()


class VascoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vasco/Kermi Ventilation."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                unique_id = await _validate_and_get_unique_id(self.hass, user_input)
            except VascoAuthError:
                errors["base"] = "invalid_auth"
            except (VascoConnectionError, VascoApiError):
                errors["base"] = "cannot_connect"
            except NoDevicesFound:
                errors["base"] = "no_devices_found"
            except Exception:  # noqa: BLE001 - config flows must not raise
                _LOGGER.exception("Unexpected error validating Vasco credentials")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_EMAIL], data=user_input)

        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            data = {
                CONF_EMAIL: reauth_entry.data[CONF_EMAIL],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            try:
                await _validate_and_get_unique_id(self.hass, data)
            except VascoAuthError:
                errors["base"] = "invalid_auth"
            except (VascoConnectionError, VascoApiError):
                errors["base"] = "cannot_connect"
            except NoDevicesFound:
                errors["base"] = "no_devices_found"
            except Exception:  # noqa: BLE001 - config flows must not raise
                _LOGGER.exception("Unexpected error during Vasco reauth")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(reauth_entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}),
            errors=errors,
            description_placeholders={"email": reauth_entry.data[CONF_EMAIL]},
        )

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return VascoOptionsFlow()


class VascoOptionsFlow(OptionsFlow):
    """Options: how often to poll the account, and live updates.

    self.config_entry is provided by Home Assistant; assigning it in
    __init__ raises AttributeError since HA 2025.12.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self.config_entry.options
        current = options.get(CONF_SCAN_INTERVAL_SECONDS, 60)
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL_SECONDS, default=current): vol.All(
                    vol.Coerce(int), vol.Range(min=30, max=600)
                ),
                vol.Required(
                    CONF_LIVE_UPDATES,
                    default=options.get(CONF_LIVE_UPDATES, DEFAULT_LIVE_UPDATES),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
