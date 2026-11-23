"""Config, reauth and options flows."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vasco_ventilation.const import (
    CONF_LIVE_UPDATES,
    CONF_SCAN_INTERVAL_SECONDS,
    DOMAIN,
)
from custom_components.vasco_ventilation.exceptions import (
    VascoApiError,
    VascoAuthError,
    VascoConnectionError,
)

USER_INPUT = {"email": "User@Example.com", "password": "secret"}


@pytest.fixture
def flow_client(account_config: dict) -> Any:
    with patch(
        "custom_components.vasco_ventilation.config_flow.VascoApiClient", autospec=True
    ) as cls:
        client = cls.return_value
        client.async_get_account_configuration.return_value = account_config
        yield client


@pytest.fixture(autouse=True)
def _no_setup() -> Any:
    with patch("custom_components.vasco_ventilation.async_setup_entry", return_value=True):
        yield


async def test_user_flow(hass: HomeAssistant, flow_client: AsyncMock) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "user@example.com"


@pytest.mark.parametrize(
    ("error", "key"),
    [
        (VascoAuthError("x"), "invalid_auth"),
        (VascoConnectionError("x"), "cannot_connect"),
        (VascoApiError("x"), "cannot_connect"),
        (RuntimeError("x"), "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, flow_client: AsyncMock, error: Exception, key: str
) -> None:
    flow_client.async_login.side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": key}


async def test_user_flow_no_devices(hass: HomeAssistant, flow_client: AsyncMock) -> None:
    flow_client.async_get_account_configuration.return_value = {"deviceProperties": []}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], USER_INPUT)
    assert result["errors"] == {"base": "no_devices_found"}


async def test_reauth(
    hass: HomeAssistant, flow_client: AsyncMock, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "new-secret"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data["password"] == "new-secret"


async def test_options_flow(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Regression: the options flow crashed on HA >= 2025.12."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL_SECONDS: 120, CONF_LIVE_UPDATES: False}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options == {CONF_SCAN_INTERVAL_SECONDS: 120, CONF_LIVE_UPDATES: False}
