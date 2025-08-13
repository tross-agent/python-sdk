"""Test that imports work correctly for the excloud package."""

import pytest


def test_client_import():
    """Test that Client can be imported from excloud."""
    from excloud import Client
    assert Client is not None


def test_all_main_imports():
    """Test that all main classes and exceptions can be imported."""
    from excloud import (
        Client,
        Sandbox,
        ExcloudException,
        AuthenticationError,
        SandboxCreationError,
        SessionError,
        ConnectionError,
        SandboxNotFoundError,
        CommandExecutionError,
    )

    # Check that all imports are not None
    assert Client is not None
    assert Sandbox is not None
    assert ExcloudException is not None
    assert AuthenticationError is not None
    assert SandboxCreationError is not None
    assert SessionError is not None
    assert ConnectionError is not None
    assert SandboxNotFoundError is not None
    assert CommandExecutionError is not None


def test_version_import():
    """Test that version can be imported."""
    import excloud
    assert hasattr(excloud, '__version__')
    assert excloud.__version__ == "0.1.0"


def test_client_instantiation():
    """Test that Client can be instantiated with minimal parameters."""
    from excloud import Client

    # This should not raise an exception
    client = Client(api_key="test_key")
    assert client.api_key == "test_key"
    assert client.base_url == "https://compute.excloud.in"
    assert client.timeout == 10


def test_client_custom_params():
    """Test that Client can be instantiated with custom parameters."""
    from excloud import Client

    client = Client(
        api_key="custom_key",
        base_url="https://custom.example.com",
        timeout=30
    )
    assert client.api_key == "custom_key"
    assert client.base_url == "https://custom.example.com"
    assert client.timeout == 30


def test_create_function():
    """Test that the create convenience function works."""
    from excloud import create

    client = create(api_key="test_key")
    assert client is not None
    assert client.api_key == "test_key"


def test_exception_inheritance():
    """Test that custom exceptions inherit from ExcloudException."""
    from excloud import (
        ExcloudException,
        AuthenticationError,
        SandboxCreationError,
        SessionError,
        ConnectionError,
        SandboxNotFoundError,
        CommandExecutionError,
    )

    # Test that all specific exceptions inherit from ExcloudException
    assert issubclass(AuthenticationError, ExcloudException)
    assert issubclass(SandboxCreationError, ExcloudException)
    assert issubclass(SessionError, ExcloudException)
    assert issubclass(ConnectionError, ExcloudException)
    assert issubclass(SandboxNotFoundError, ExcloudException)
    assert issubclass(CommandExecutionError, ExcloudException)
