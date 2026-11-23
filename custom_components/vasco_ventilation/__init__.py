"""The Vasco/Kermi Ventilation integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import VascoApiClient
from .const import (
    CONF_LIVE_UPDATES,
    CONF_SCAN_INTERVAL_SECONDS,
    DEFAULT_LIVE_UPDATES,
    DEFAULT_SCAN_INTERVAL,
)
from .coordinator import VascoConfigEntry, VascoCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SELECT,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]


async def async_setup_entry(hass: HomeAssistant, entry: VascoConfigEntry) -> bool:
    """Set up Vasco/Kermi Ventilation from a config entry."""
    session = async_get_clientsession(hass)
    client = VascoApiClient(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])

    scan_interval_seconds = entry.options.get(CONF_SCAN_INTERVAL_SECONDS)
    update_interval = (
        timedelta(seconds=scan_interval_seconds) if scan_interval_seconds else DEFAULT_SCAN_INTERVAL
    )

    coordinator = VascoCoordinator(hass, entry, client, update_interval)
    # Raises ConfigEntryAuthFailed (bad credentials -> triggers reauth) or
    # ConfigEntryNotReady (network hiccup -> HA retries setup later) as
    # appropriate; both are handled by the DataUpdateCoordinator base class.
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _async_remove_stale_fan_entities(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if entry.options.get(CONF_LIVE_UPDATES, DEFAULT_LIVE_UPDATES):
        coordinator.async_start_live_updates()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VascoConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: VascoConfigEntry) -> None:
    """Reload the entry when its options change (e.g. scan interval)."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_remove_stale_fan_entities(hass: HomeAssistant, entry: VascoConfigEntry) -> None:
    """Drop the fan entity left behind by versions before 0.2.0.

    0.2.0 replaced it with a select entity, since Home Assistant always
    renders a fan's entity row with an on/off toggle the unit doesn't
    support. Without this, the orphaned fan entity would linger in the
    registry forever, permanently unavailable.
    """
    entity_registry = er.async_get(hass)
    for entry_entity in er.async_entries_for_config_entry(entity_registry, entry.entry_id):
        if entry_entity.domain == "fan":
            entity_registry.async_remove(entry_entity.entity_id)
