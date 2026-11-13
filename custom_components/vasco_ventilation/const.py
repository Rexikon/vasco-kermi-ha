"""Constants for the Vasco/Kermi Ventilation integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "vasco_ventilation"

API_BASE = "https://vasco.iqloud.eu/api"
USER_AGENT = "Dart/3.8 (dart:io)"

DEFAULT_SCAN_INTERVAL = timedelta(seconds=60)
MIN_SCAN_INTERVAL = timedelta(seconds=30)
MAX_SCAN_INTERVAL = timedelta(seconds=600)
CONF_SCAN_INTERVAL_SECONDS = "scan_interval_seconds"

# Confirmed live against a real VMD-17RPS01 ("Vasco X500") unit via MITM
# capture of the official app (2026-08-25): the requestedLevel enum used by
# the REST/account API is NOT the raw value the bridge expects on its
# writeData command.
#
# Mapped live on an X425 (VMD-17RPS01) by writing each wire value and
# reading the cloud `level` back, cross-checked against what the official
# app shows (2026-11-13):
#
#   wire 2 / 3 / 4 -> level 1 / 2 / 3   Low / Medium / High
#   wire 6         -> level 4           Holidays ("Wakacje", speedRatio*6)
#   wire 7         -> level 5           Guests ("Goscie", speedRatio*7)
#   wire 1, 5, 8   -> acknowledged by the bridge, ignored by the unit
#
# Wire 5 is what the official app sends for "Automatic"; the X425 without a
# humidity/CO2 sensor ignores it, so Auto is not offered here.
#
# The app's timed boost ("Regulator") is not a requestedLevel write at all:
# it writes overrideTimeSpeed3 = minutes, and the unit reports level 13
# (High, timed) until the timer runs out or another level is written.
LEVEL_LOW = 1
LEVEL_MEDIUM = 2
LEVEL_HIGH = 3
LEVEL_HOLIDAYS = 4
LEVEL_GUESTS = 5
LEVEL_BOOST = 13

LEVEL_NAMES: dict[int, str] = {
    LEVEL_LOW: "Low",
    LEVEL_MEDIUM: "Medium",
    LEVEL_HIGH: "High",
    LEVEL_HOLIDAYS: "Holidays",
    LEVEL_GUESTS: "Guests",
    LEVEL_BOOST: "Boost",
}
NAME_TO_LEVEL: dict[str, int] = {name: level for level, name in LEVEL_NAMES.items()}

# Cloud level -> raw wire value sent in the requestedLevel writeData frame.
WIRE_LEVEL_OFFSET: dict[int, int] = {
    LEVEL_LOW: 2,
    LEVEL_MEDIUM: 3,
    LEVEL_HIGH: 4,
    LEVEL_HOLIDAYS: 6,
    LEVEL_GUESTS: 7,
}

# The presets this integration writes through the select entity. Boost is
# shown read-only there and started with its own button (see button.py).
SETTABLE_LEVELS: tuple[int, ...] = (
    LEVEL_LOW,
    LEVEL_MEDIUM,
    LEVEL_HIGH,
    LEVEL_HOLIDAYS,
    LEVEL_GUESTS,
)

# manualSettingActiveTill values sent with a level write: how long the
# level holds before the schedule takes over again. Any other value is an
# end time in epoch milliseconds. Confirmed live on an X425: the cloud
# reschedules the next event accordingly and the unit returns to the
# schedule's level when a timed level ends.
MANUAL_UNTIL_NEXT_SCHEDULE = 0
MANUAL_PERMANENT = -1

# Options of the "manual level duration" select -> minutes (None = special).
MANUAL_DURATION_UNTIL_SCHEDULE = "until_schedule"
MANUAL_DURATION_PERMANENT = "permanent"
MANUAL_DURATION_MINUTES: dict[str, int | None] = {
    MANUAL_DURATION_UNTIL_SCHEDULE: None,
    MANUAL_DURATION_PERMANENT: None,
    "5m": 5,
    "10m": 10,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "8h": 480,
    "24h": 1440,
}

# Timed functions: writing the duration in minutes to these parameters
# starts them, exactly as the official app does. The unit ends them itself.
PARAM_BOOST_MINUTES = "overrideTimeSpeed3"
PARAM_FIREPLACE_MINUTES = "fireplaceModeTime"
DEFAULT_BOOST_MINUTES = 30
DEFAULT_FIREPLACE_MINUTES = 10

PRODUCT_CATEGORY_VENTILATION = "VENTILATION"

MANUFACTURER = "Vasco"
