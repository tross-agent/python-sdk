"""
Custom exceptions for the Excloud SDK.
"""


class ExcloudException(Exception):
    """Base exception for all Excloud SDK errors."""

    pass


class AuthenticationError(ExcloudException):
    """Raised when API authentication fails."""

    pass


class SandboxCreationError(ExcloudException):
    """Raised when sandbox creation fails."""

    pass


class SessionError(ExcloudException):
    """Raised when SSH session operations fail."""

    pass


class ConnectionError(ExcloudException):
    """Raised when WebSocket connection fails."""

    pass


class SandboxNotFoundError(ExcloudException):
    """Raised when sandbox doesn't exist."""

    pass


class CommandExecutionError(ExcloudException):
    """Raised when command execution fails."""

    pass
