# Excloud Python SDK

[![PyPI version](https://badge.fury.io/py/excloud.svg)](https://badge.fury.io/py/excloud)
[![Python versions](https://img.shields.io/pypi/pyversions/excloud.svg)](https://pypi.org/project/excloud/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Python SDK for creating and managing cloud sandboxes with Excloud. Easily spin up isolated computing environments for development, testing, and automation.

## Installation

```bash
pip install excloud
```

## Quick Start

```python
from excloud import Client

# Initialize client with your API key
client = Client(api_key="your_api_key_here")

# Create a sandbox
sandbox = client.create()
print(f"Sandbox created: {sandbox.name}")

# Execute commands in the sandbox
result = sandbox.run("python --version")
print(result)

# Clean up
sandbox.destroy()
```

## Usage with Context Manager

For automatic cleanup, use the context manager:

```python
from excloud import Client

client = Client(api_key="your_api_key")

with client.create() as sandbox:
    # Execute commands
    result = sandbox.run("ls -la")
    print(result)

# Sandbox is automatically destroyed when exiting the context
```

## Features

- **Easy Sandbox Management**: Create, manage, and destroy cloud sandboxes with simple API calls
- **Command Execution**: Run shell commands and scripts in isolated environments
- **Real-time Communication**: WebSocket-based real-time command execution and output streaming
- **Context Manager Support**: Automatic resource cleanup with Python context managers
- **Comprehensive Error Handling**: Detailed exceptions for different failure scenarios
- **Logging Support**: Built-in logging for debugging and monitoring

## API Reference

### Client

```python
from excloud import Client

client = Client(
    api_key="your_api_key",
    base_url="https://compute.excloud.in",  # Optional, defaults to production URL
    timeout=10  # Optional, request timeout in seconds
)
```

### Methods

#### `client.create()`
Creates a new sandbox and returns a `Sandbox` instance.

#### `client.get(sandbox_id)`
Retrieves an existing sandbox by ID.

#### `client.list()`
Lists all sandboxes associated with your account.

### Sandbox

#### `sandbox.run(command)`
Executes a command in the sandbox and returns the result.

```python
result = sandbox.run("echo 'Hello, World!'")
print(result)  # Output from the command
print(result.exit_code)  # Exit code (0 for success)
```

#### `sandbox.upload_file(local_path, remote_path)`
Uploads a file from your local machine to the sandbox.

#### `sandbox.download_file(remote_path, local_path)`
Downloads a file from the sandbox to your local machine.

#### `sandbox.destroy()`
Destroys the sandbox and cleans up all resources.

## Error Handling

The SDK provides specific exceptions for different error scenarios:

```python
from excloud import Client
from excloud import (
    AuthenticationError,
    SandboxCreationError,
    CommandExecutionError,
    ConnectionError,
    SandboxNotFoundError
)

try:
    client = Client(api_key="invalid_key")
    sandbox = client.create()
except AuthenticationError:
    print("Invalid API key")
except SandboxCreationError:
    print("Failed to create sandbox")
except ConnectionError:
    print("Network connection failed")
```

## Configuration

### Environment Variables

You can also configure the client using environment variables:

```bash
export EXCLOUD_API_KEY="your_api_key"
export EXCLOUD_BASE_URL="https://compute.excloud.in"
```

```python
import os
from excloud import Client

# Client will automatically use environment variables
client = Client(api_key=os.getenv("EXCLOUD_API_KEY"))
```

## Requirements

- Python 3.7+
- `requests>=2.25.0`
- `websockets>=11.0`

## Examples

### Running a Python Script

```python
from excloud import Client

client = Client(api_key="your_api_key")

with client.create() as sandbox:
    # Create a Python script
    script = """
import json
data = {"message": "Hello from sandbox!", "status": "success"}
print(json.dumps(data, indent=2))
"""

    # Write script to file
    sandbox.run(f"cat > script.py << 'EOF'\n{script}\nEOF")

    # Execute the script
    result = sandbox.run("python script.py")
    print(result)
```

### Installing and Using Packages

```python
from excloud import Client

client = Client(api_key="your_api_key")

with client.create() as sandbox:
    # Install packages
    sandbox.run("pip install numpy pandas")

    # Use the packages
    result = sandbox.run("python -c 'import numpy as np; print(np.__version__)'")
    print(f"NumPy version: {result}")
```

## Support

- **Documentation**: [https://docs.excloud.in](https://docs.excloud.in)
- **Issues**: [GitHub Issues](https://github.com/excloud/excloud-python/issues)
- **Support**: support@excloud.in

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Changelog

### 0.1.0
- Initial release
- Basic sandbox creation and management
- Command execution support
- WebSocket-based real-time communication
- Context manager support
