"""Shared fixtures. All device data here is synthetic."""

from __future__ import annotations

import copy
from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vasco_ventilation.const import DOMAIN

SERIAL = "TESTSERIAL001"

DEVICE: dict[str, Any] = {
    "serial": SERIAL,
    "name": "Test unit",
    "productCategory": "VENTILATION",
    "productTypeString": "VMD-17RPS01",
    "productType": "0x0001c83a",
    "swVersion": 25,
    "hwVersion": 3,
    "modbusAddress": 2,
    "macAddress": "00:00:00:00:00:01",
    "level": 2,
    "controlMode": "schedule",
    "nextValue": 4,
    "timestampOfNextEvent": 1,
    "manualSettingActiveTill": 0,
    "actualFanSpeedInlet": 70,
    "actualFanSpeedExhaust": 70,
    "actualInletFlow": 42.77,
    "actualExhaustFlow": 76.38,
    "qHighSupply": 7,
    "qHighExhaust": 500,
    "qMax": 500,
    "indoorTemperature": 21.3,
    "outdoorTemperature": 10.0,
    "supplyTemperature": 21.0,
    "exhaustTemperature": 18.0,
    "bypassPosition": 0,
    "preHeaterDemand": 0xEF,
    "filterReplaceTime": 365,
    "filterDirty": 0,
    "faultStatus": 0,
    "defrost": 0,
    "fireplaceModeStatus": 0,
    "fireplaceModeTime": 5,
    "overrideTimeSpeed3": 30,
}

ACCOUNT_CONFIG: dict[str, Any] = {
    "deviceProperties": [DEVICE],
    "bridges": [
        {
            "macAddress": "00:00:00:00:00:01",
            "appServerURL": "wss://appserver.example.invalid:443",
            "bridgeToken": "bridge-token",
            "externalIP": "192.0.2.10",
        }
    ],
    "weatherAndGeoData": {"city": "Testville", "location": "[1.0,2.0]"},
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Load custom_components/ in every test."""


@pytest.fixture
def account_config() -> dict[str, Any]:
    return copy.deepcopy(ACCOUNT_CONFIG)


@pytest.fixture
def config_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="user@example.com",
        unique_id="user@example.com",
        data={"email": "user@example.com", "password": "secret"},
    )


@pytest.fixture
def mock_client(account_config: dict[str, Any]) -> Generator[AsyncMock]:
    """Patch the API client used by the integration (not the config flow)."""
    with patch("custom_components.vasco_ventilation.VascoApiClient", autospec=True) as cls:
        client = cls.return_value
        client.async_get_account_configuration.return_value = account_config
        yield client
