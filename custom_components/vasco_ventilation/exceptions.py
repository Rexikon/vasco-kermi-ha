"""Exceptions for the Vasco Ventilation integration."""

from __future__ import annotations


class VascoError(Exception):
    """Base error for the Vasco cloud API."""


class VascoAuthError(VascoError):
    """Raised when login fails (bad credentials or an expired/rejected token)."""


class VascoConnectionError(VascoError):
    """Raised on network failures talking to vasco.iqloud.eu."""


class VascoApiError(VascoError):
    """Raised when the API responds but reports a non-success status
    that isn't a connection or auth problem."""


class VascoNoDevicesError(VascoError):
    """Raised when the account has no ventilation device."""
