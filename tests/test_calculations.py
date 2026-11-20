"""Airflow and other value calculations, checked against the official app."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from custom_components.vasco_ventilation.sensor import (
    _EXHAUST_SPEED_KEYS,
    _INLET_SPEED_KEYS,
    _boost_end,
    _flow,
    _mean_flow,
    _preheater,
)


@pytest.mark.parametrize(
    ("device", "app_value"),
    [
        # X500 with a mis-set 7 m3/h supply maximum (the app showed 177.4)
        (
            {
                "actualFanSpeedInlet": 70,
                "actualFanSpeedExhaust": 70,
                "qHighSupply": 7,
                "qHighExhaust": 500,
            },
            177.4,
        ),
        # X425, PR #3: level 1 and level 2
        (
            {
                "actualFanSpeedInlet": 26,
                "actualFanSpeedExhaust": 27,
                "qHighSupply": 400,
                "qHighExhaust": 405,
            },
            106.6,
        ),
        (
            {
                "actualFanSpeedInlet": 60,
                "actualFanSpeedExhaust": 61,
                "qHighSupply": 400,
                "qHighExhaust": 405,
            },
            243.5,
        ),
        # 225 Compact, issue #1: other field names, absoluteMaximumFlow
        (
            {"actualInletFanSpeed": 60, "actualExhaustFanSpeed": 60, "absoluteMaximumFlow": 225},
            135.0,
        ),
    ],
)
def test_mean_flow_matches_app(device: dict, app_value: float) -> None:
    assert _mean_flow(device) == app_value


def test_mean_flow_missing_inputs() -> None:
    assert _mean_flow({}) is None
    assert _mean_flow({"actualFanSpeedInlet": 50, "qHighSupply": 400}) is None


def test_flow_zero_maximum_falls_through() -> None:
    device = {"actualFanSpeedInlet": 60, "qHighSupply": 0, "absoluteMaximumFlow": 225}
    assert _flow(device, _INLET_SPEED_KEYS, "qHighSupply", "actualInletFlow") == 135.0


def test_flow_raw_field_fallback() -> None:
    device = {"actualExhaustFlow": 10}
    assert _flow(device, _EXHAUST_SPEED_KEYS, "qHighExhaust", "actualExhaustFlow") == 10


def test_flow_rounds_to_one_decimal() -> None:
    device = {"actualFanSpeedExhaust": 27, "qHighExhaust": 405}
    assert _flow(device, _EXHAUST_SPEED_KEYS, "qHighExhaust", "actualExhaustFlow") == 109.3


def test_preheater_not_present() -> None:
    assert _preheater({"preHeaterDemand": 0xEF}) is None
    assert _preheater({"preHeaterDemand": 42}) == 42


def test_boost_end_only_while_boosting() -> None:
    till = 1_800_000_000_000
    assert _boost_end({"level": 13, "manualSettingActiveTill": till}) == datetime.fromtimestamp(
        till / 1000, tz=UTC
    )
    assert _boost_end({"level": 2, "manualSettingActiveTill": till}) is None
    assert _boost_end({"level": 13, "manualSettingActiveTill": -1}) is None
