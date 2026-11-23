"""Live updates pushed over the bridge WebSocket."""

from __future__ import annotations

import asyncio
import copy
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vasco_ventilation.const import CONF_LIVE_UPDATES
from custom_components.vasco_ventilation.coordinator import (
    LIVE_POLL_INTERVAL,
    apply_value_changed,
)
from custom_components.vasco_ventilation.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import ACCOUNT_CONFIG


def _frame(parameter: str, value: Any, index: int = 0) -> dict[str, Any]:
    return {
        "functionName": "valueChanged",
        "itemName": "deviceProperties",
        "index": index,
        "parameterName": parameter,
        "value": value,
    }


def test_apply_value_changed_updates_a_copy() -> None:
    data = copy.deepcopy(ACCOUNT_CONFIG)
    updated = apply_value_changed(data, _frame("actualFanSpeedInlet", 40))
    assert updated is not None
    assert updated["deviceProperties"][0]["actualFanSpeedInlet"] == 40
    assert data["deviceProperties"][0]["actualFanSpeedInlet"] == 70
    assert updated["bridges"] is data["bridges"]


def test_apply_value_changed_adds_a_new_field() -> None:
    updated = apply_value_changed(copy.deepcopy(ACCOUNT_CONFIG), _frame("requestedLevel", None))
    assert updated is not None
    assert updated["deviceProperties"][0]["requestedLevel"] is None


def test_apply_value_changed_ignores_other_frames() -> None:
    data = copy.deepcopy(ACCOUNT_CONFIG)
    assert apply_value_changed(data, _frame("actualFanSpeedInlet", 70)) is None  # unchanged
    assert apply_value_changed(data, _frame("level", 3, index=1)) is None  # no such device
    assert apply_value_changed(data, _frame("level", 3, index=-1)) is None
    assert apply_value_changed(data, {**_frame("level", 3), "itemName": "bridges"}) is None
    assert apply_value_changed(data, {**_frame("level", 3), "functionName": "dataWritten"}) is None
    assert (
        apply_value_changed(data, {"functionName": "accountPropertiesChanged", "payload": "[]"})
        is None
    )


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_pushed_frames_update_entities(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    pushed = asyncio.Event()

    async def listen(config, device, on_frame, on_connected=None) -> None:
        on_connected()
        on_frame(_frame("actualFanSpeedInlet", 40))
        on_frame(_frame("level", 3))
        pushed.set()
        await asyncio.Event().wait()  # stay connected

    mock_client.async_listen.side_effect = listen
    await _setup(hass, config_entry)
    await asyncio.wait_for(pushed.wait(), 1)
    await hass.async_block_till_done()

    assert hass.states.get("select.test_unit").state == "high"
    # 40 % of the 7 m3/h configured for 100 % supply.
    assert hass.states.get("sensor.test_unit_inlet_airflow").state == "2.8"
    diag = await async_get_config_entry_diagnostics(hass, config_entry)
    assert diag["live_connections"] == 1

    assert await hass.config_entries.async_unload(config_entry.entry_id)


async def test_polling_slows_down_while_connected(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_client: AsyncMock
) -> None:
    connected = asyncio.Event()
    drop = asyncio.Event()
    calls = 0

    async def listen(config, device, on_frame, on_connected=None) -> None:
        nonlocal calls
        calls += 1
        if calls > 1:
            await asyncio.Event().wait()  # reconnect attempt: stay pending
        on_connected()
        connected.set()
        await drop.wait()  # then the server closes the connection

    mock_client.async_listen.side_effect = listen
    await _setup(hass, config_entry)
    coordinator = config_entry.runtime_data
    await asyncio.wait_for(connected.wait(), 1)
    assert coordinator.update_interval == LIVE_POLL_INTERVAL

    polls = mock_client.async_get_account_configuration.call_count
    drop.set()
    await hass.async_block_till_done()
    assert coordinator.update_interval == timedelta(seconds=60)
    # A dropped connection triggers a catch-up poll right away.
    assert mock_client.async_get_account_configuration.call_count == polls + 1

    assert await hass.config_entries.async_unload(config_entry.entry_id)


async def test_live_updates_can_be_turned_off(hass: HomeAssistant, mock_client: AsyncMock) -> None:
    entry = MockConfigEntry(
        domain="vasco_ventilation",
        title="user@example.com",
        unique_id="user@example.com",
        data={"email": "user@example.com", "password": "secret"},
        options={CONF_LIVE_UPDATES: False},
    )
    await _setup(hass, entry)
    mock_client.async_listen.assert_not_called()
