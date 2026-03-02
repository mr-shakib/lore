"""
loremem exceptions.

These are INTERNAL — never surfaced to SDK callers.
All public methods catch every exception, log a warning, and return a safe default.
"""


class LoreMemError(Exception):
    """Base exception for all loremem SDK errors."""


class AuthError(LoreMemError):
    """API key rejected or workspace not found."""


class NetworkError(LoreMemError):
    """Could not reach the Lore API."""


class TimeoutError(LoreMemError):
    """Request timed out."""


class RateLimitError(LoreMemError):
    """Workspace rate limit exceeded."""


class ServerError(LoreMemError):
    """Lore API returned a 5xx response."""
