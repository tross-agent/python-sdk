"""
Excloud SDK - Python client for managing cloud sandboxes.

Usage:
    import orca

    client = orca.Client(api_key="your_api_key")
    sandbox = client.create()

    result = sandbox.run("ls -la")
    print(result)

    sandbox.destroy()

Or using context manager:
    with client.create() as sandbox:
        result = sandbox.run("python --version")
        print(result)
"""

from .client import Client
from .exceptions import (
    AuthenticationError,
    CommandExecutionError,
    ConnectionError,
    ExcloudException,
    SandboxCreationError,
    SandboxNotFoundError,
    SessionError,
)
from .sandbox import Sandbox

__version__ = "0.1.0"
__all__ = [
    "Client",
    "Sandbox",
    "ExcloudException",
    "AuthenticationError",
    "SandboxCreationError",
    "SessionError",
    "ConnectionError",
    "SandboxNotFoundError",
    "CommandExecutionError",
]


def create(api_key: str, base_url: str = "https://compute.excloud.in") -> "Client":
    """
    Create a new Excloud client.

    Args:
        api_key: API key for authentication
        base_url: Base URL of the API

    Returns:
        Client instance
    """
    return Client(api_key=api_key, base_url=base_url)
