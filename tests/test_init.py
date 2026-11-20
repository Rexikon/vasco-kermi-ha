"""Setup, entities, writes and diagnostics with a mocked API client."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vasco_ventilation.const import DOMAIN
from custom_components.vasco_ventilation.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.vasco_ventilation.exceptions import (
    VascoAuthError,
    VascoConnectionError,
)

from .conftest import SERIAL

LEVEL = "select.test_unit"


@pytest.fixture(autouse=True)
def _no_confirm_wait() -> Any:
    """Don't sleep between post-write polls."""
    with patch("custom_components.vasco_ventilation.coordinator._CONFIRM_POLL_DELAY", 0):
        yield


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_and_unload(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await _setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.runtime_data.data["deviceProperties"][0]["serial"] == SERIAL

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_entities(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await _setup(hass, config_entry)

    assert hass.states.get("sensor.test_unit_airflow").state == "177.4"
    assert hass.states.get("sensor.test_unit_inlet_airflow").state == "4.9"
    assert hass.states.get("sensor.test_unit_exhaust_airflow").state == "350.0"
    assert hass.states.get("sensor.test_unit_preheater_demand").state == "unknown"

    level = hass.states.get(LEVEL)
    assert level.state == "medium"
    assert level.attributes["next_scheduled_level"] == "high"  # wire 4

    (device,) = dr.async_entries_for_config_entry(dr.async_get(hass), config_entry.entry_id)
    assert (DOMAIN, SERIAL) in device.identifiers
    assert device.serial_number == SERIAL
    assert device.hw_version == "3"


async def test_select_level_writes_with_duration(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await _setup(hass, config_entry)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.test_unit_manual_level_duration", "option": "permanent"},
        blocking=True,
    )
    await hass.services.async_call(
        "select", "select_option", {"entity_id": LEVEL, "option": "high"}, blocking=True
    )
    args = mock_client.async_set_level.call_args.args
    assert args[2:] == (3, -1)


async def test_boost_not_selectable(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await _setup(hass, config_entry)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            "select", "select_option", {"entity_id": LEVEL, "option": "boost"}, blocking=True
        )
    assert err.value.translation_key == "level_not_settable"
    mock_client.async_set_level.assert_not_called()


async def test_write_error_is_readable(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await _setup(hass, config_entry)
    mock_client.async_set_level.side_effect = VascoConnectionError("boom")
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            "select", "select_option", {"entity_id": LEVEL, "option": "low"}, blocking=True
        )
    assert err.value.translation_key == "write_failed"


async def test_write_auth_error_starts_reauth(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await _setup(hass, config_entry)
    mock_client.async_write_parameter.side_effect = VascoAuthError("nope")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button", "press", {"entity_id": "button.test_unit_boost"}, blocking=True
        )
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_unknown_level_warns_once(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_client: AsyncMock,
    account_config: dict,
    caplog: pytest.LogCaptureFixture,
) -> None:
    account_config["deviceProperties"][0]["level"] = 21
    await _setup(hass, config_entry)
    assert hass.states.get(LEVEL).state == "unknown"
    await config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert caplog.text.count("unknown ventilation level 21") == 1


async def test_diagnostics_redacts_location(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    await _setup(hass, config_entry)
    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    text = str(diag)
    for secret in (
        "192.0.2.10",
        "Testville",
        "[1.0,2.0]",
        "secret",
        "user@example.com",
        "bridge-token",
        SERIAL,
        "00:00:00:00:00:01",
    ):
        assert secret not in text, secret
    assert diag["account_configuration"]["deviceProperties"][0]["qHighExhaust"] == 500
