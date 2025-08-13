#!/usr/bin/env python3
"""
Simple example for the Excloud SDK.
"""

import os
import excloud as orca


def main():
    # Get API key from environment
    api_key = os.getenv("EXCLOUD_API_KEY")
    if not api_key:
        print("Please set EXCLOUD_API_KEY environment variable")
        return

    # Create client
    client = orca.Client(api_key=api_key)
    print("✓ Client created")

    # Test connection first
    if not client.test_connection():
        print("❌ Connection failed - check API key and network")
        return

    print("✓ Connection test passed")

    # Create sandbox and run commands
    with client.create() as sandbox:
        print(f"✓ Created sandbox: {sandbox.name}")

        # Run some basic commands
        result = sandbox.run("whoami")
        print(f"User: {result}")

        result = sandbox.run("python3 --version")
        print(f"Python: {result}")


        result = sandbox.run("ls -la")
        print(f"Files:\n{result}")

    print("✓ Sandbox cleaned up")


if __name__ == "__main__":
    main()
