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
# writeData command -- the wire value is the cloud level + 1. Wire value 1
# is reserved for something else (observed: it resets manualSettingActiveTill
# to 0 / hands control back to the schedule, it does not set a fan speed).
#
# Only levels 1-3 have a confirmed wire mapping. Auto (4), Holidays (6) and
# Guests (7) exist in the account API but their wire encoding has not been
# verified against real traffic -- don't guess, they're deliberately left
# out of what this integration can *set*.
LEVEL_LOW = 1
LEVEL_MEDIUM = 2
LEVEL_HIGH = 3
LEVEL_AUTO = 4
LEVEL_HOLIDAYS = 6
LEVEL_GUESTS = 7

LEVEL_NAMES: dict[int, str] = {
    LEVEL_LOW: "Low",
    LEVEL_MEDIUM: "Medium",
    LEVEL_HIGH: "High",
    LEVEL_AUTO: "Auto",
    LEVEL_HOLIDAYS: "Holidays",
    LEVEL_GUESTS: "Guests",
}
NAME_TO_LEVEL: dict[str, int] = {name: level for level, name in LEVEL_NAMES.items()}

# Cloud requestedLevel enum -> raw wire value sent in the writeData frame.
# Confirmed for 1/2/3 only -- see the note above.
WIRE_LEVEL_OFFSET: dict[int, int] = {
    LEVEL_LOW: 2,
    LEVEL_MEDIUM: 3,
    LEVEL_HIGH: 4,
}

# The only presets this integration will actually write. Reading back a
# level outside this set (the unit was put into Auto/Holidays/Guests from
# the official app, or a "boost" state) is still displayed -- see select.py.
SETTABLE_LEVELS: tuple[int, ...] = (LEVEL_LOW, LEVEL_MEDIUM, LEVEL_HIGH)

PRODUCT_CATEGORY_VENTILATION = "VENTILATION"

MANUFACTURER = "Vasco"
