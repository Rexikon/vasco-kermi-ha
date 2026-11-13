# Vasco/Kermi Ventilation for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![hassfest](https://github.com/Rexikon/vasco-kermi-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/Rexikon/vasco-kermi-ha/actions/workflows/validate.yml)
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Rexikon&repository=vasco-kermi-ha&category=Integration)

A [Home Assistant](https://www.home-assistant.io/) integration for Vasco
heat-recovery ventilation units (tested against a **VMD-17RPS01**, sold as
the **Vasco X500**) via the `vasco.iqloud.eu` cloud API — the same backend
the official **Vasco** phone app talks to.

This is an **unofficial, reverse-engineered** integration. It is not made,
endorsed, or supported by Vasco.

## Features

- **Ventilation level control** — a select entity for Low, Medium, High,
  Holidays, or Guests, with its state (and history) tracked like any other
  entity — no on/off toggle, since the unit doesn't support one.
- **Manual level duration** — like the app's prompt: until the next schedule
  change (default), permanently, or for 1/2/4/8/24 hours.
- **Timed functions** — Boost and Fireplace mode buttons, the same as the
  official app's "Regulator" and "Kominek". Boost runs for the time stored
  in the unit (30 min by default); Fireplace mode for the time last picked
  in the app.
- **Sensors** — indoor/outdoor/supply/exhaust temperature, inlet/exhaust
  airflow (m³/h), inlet/exhaust fan speed (%), bypass position (%), preheater
  demand (%), boost end time, filter replace interval.
- **Binary sensors** — filter dirty, fault, defrost active, fireplace mode
  active.
- **Diagnostics** — download a redacted diagnostics dump from the entry's
  three-dot menu for bug reports.
- Polls the account once a minute by default (configurable in the
  integration's Options).

## Installation
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Rexikon&repository=vasco-kermi-ha&category=Integration)

### HACS (recommended)

1. In Home Assistant, go to **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/Rexikon/vasco-kermi-ha` with category **Integration**.
3. Search for **Vasco/Kermi Ventilation** in HACS and install it.
4. Restart Home Assistant.

### Manual

1. Copy `custom_components/vasco_ventilation` into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## Setup

**Settings → Devices & services → Add integration → Vasco/Kermi Ventilation**,
then enter the same email and password you use in the official Vasco app.

The polling interval (default 60s, matching the official app) can be changed
afterwards from the integration's **Configure** button.

## Known limitations

This protocol was reverse-engineered by capturing the official app's real
network traffic — some things are deliberately **not** implemented because
they were never confirmed to work correctly, rather than shipping a guess:

- **No Auto mode.** The official app's "Automatic" sends a value that an
  X425 without a humidity/CO2 sensor ignores, so it isn't offered.
- **Holidays, Guests, Boost and Fireplace mode were mapped on an X425**
  (`VMD-17RPS01`). Other models may encode them differently; reports from
  other units are welcome.
- **Fireplace mode can't be stopped early.** The unit ends it when its time
  is up; changing the level meanwhile works but doesn't end it.
- **No "off" state.** A heat-recovery ventilation unit doesn't have a
  confirmed off command, so the level is exposed as a `select` entity
  rather than a `fan` — Home Assistant would otherwise show an on/off
  toggle the unit can't act on. Change the level via the select's dropdown
  instead.
- **Level changes are not always instant.** The vendor's own protocol is
  occasionally unreliable at the RF/bridge layer, independent of anything
  this integration does — the same behavior is visible in the official app.
  A level write here polls for up to ~18s to reflect success quickly; if the
  unit doesn't confirm within that window, a warning is logged (the entity
  will still update whenever it *does* catch up on the next regular poll).
- **`controlMode` is intentionally left untouched.** The official app never
  switches it to `"manual"` and neither does this integration. How long a
  manual level holds is set by `manualSettingActiveTill` instead (0 = until
  the next schedule change, -1 = permanently, otherwise an end time in epoch
  ms), which the "Manual level duration" select controls.

Contributions that nail down any of the above with a real MITM capture are
very welcome.

## Entities

| Platform | Entity | Notes |
|---|---|---|
| `select` | Ventilation level | Options: Low / Medium / High / Holidays / Guests (Boost shown read-only while running) |
| `select` | Manual level duration | config: until next schedule change / permanently / 1–24 h; applies to the next level change |
| `button` | Boost | timed High (the app's "Regulator"); select a level to stop it early |
| `button` | Fireplace mode | timed overpressure (the app's "Kominek") |
| `sensor` | Indoor / outdoor / supply / exhaust temperature | °C |
| `sensor` | Inlet / exhaust airflow | m³/h |
| `sensor` | Inlet / exhaust fan speed | % (diagnostic) |
| `sensor` | Bypass position | % (diagnostic) |
| `sensor` | Preheater demand | % (diagnostic), unknown when no preheater is fitted |
| `sensor` | Boost ends | timestamp, only while Boost runs |
| `sensor` | Filter replace interval | days (diagnostic) |
| `binary_sensor` | Filter dirty | Brak / Tak |
| `binary_sensor` | Fault | Brak / Tak |
| `binary_sensor` | Defrost active | diagnostic |
| `binary_sensor` | Fireplace boost active | diagnostic |

## Support

Found this useful? You're welcome to sponsor continued work via the
**Sponsor** button on the GitHub repo.

Bug reports and pull requests: <https://github.com/Rexikon/vasco-kermi-ha/issues>

## License

[MIT](LICENSE)
