"""
Excloud SDK Client for managing cloud sandboxes.
"""

import time
from typing import Any, Dict, Optional

import requests

from .exceptions import AuthenticationError, ExcloudException, SandboxCreationError
from .sandbox import Sandbox


class Client:
    """Main client for interacting with the Excloud API."""

    def __init__(self, api_key: str, base_url: str = "https://compute.excloud.in", timeout: int = 10):
        """
        Initialize the Excloud client.

        Args:
            api_key: API key for authentication
            base_url: Base URL of the API (default: https://compute.excloud.in)
            timeout: Request timeout in seconds (default: 10)
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        )

        # Cache for resources to avoid repeated API calls
        self._subnets_cache = None
        self._security_groups_cache = None
        self._cache_time = None
        self._cache_ttl = 300  # 5 minutes

        # Setup logger
        from .logging_config import setup_logger
        self.logger = setup_logger()
        
        self.logger.debug(f"Excloud client initialized")
        self.logger.debug(f"   Base URL: {self.base_url}")
        self.logger.debug(f"   Timeout: {self.timeout}s")
        self.logger.debug(f"   API Key: {api_key[:10]}...{api_key[-4:] if len(api_key) > 14 else '***'}")

    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make an authenticated API request."""
        url = f"{self.base_url}{endpoint}"

        # Add timeout if not already specified - use tuple for (connect, read) timeout
        if 'timeout' not in kwargs:
            kwargs['timeout'] = (5, self.timeout)  # 5s connect, 10s read

        self.logger.debug(f"Making {method} request to: {url}")
        self.logger.debug(f"Request timeout: {kwargs.get('timeout')}")
        self.logger.debug(f"Auth header present: {'Authorization' in self.session.headers}")

        try:
            response = self.session.request(method, url, **kwargs)
            self.logger.debug(f"Response status: {response.status_code}")

            if response.status_code == 401:
                raise AuthenticationError("Invalid API key or authentication failed")

            response.raise_for_status()
            return response

        except requests.exceptions.Timeout as e:
            timeout_val = kwargs.get('timeout')
            if isinstance(timeout_val, tuple):
                timeout_str = f"{timeout_val[0]}s connect, {timeout_val[1]}s read"
            else:
                timeout_str = f"{timeout_val}s"
            raise ExcloudException(f"Request timed out ({timeout_str}): {str(e)}")
        except requests.exceptions.ConnectionError as e:
            raise ExcloudException(f"Connection error: {str(e)}")
        except requests.exceptions.RequestException as e:
            raise ExcloudException(f"API request failed: {str(e)}")

    def _get_cached_resources(self) -> tuple:
        """Get cached subnets and security groups, fetching if expired."""
        self.logger.debug("Checking resource cache...")
        now = time.time()

        cache_expired = (
            self._subnets_cache is None
            or self._security_groups_cache is None
            or self._cache_time is None
            or now - self._cache_time > self._cache_ttl
        )

        if cache_expired:
            self.logger.debug(f"Cache expired or empty. Fetching fresh resources...")
            self.logger.debug(f"  - Subnets cache: {'None' if self._subnets_cache is None else 'exists'}")
            self.logger.debug(f"  - Security groups cache: {'None' if self._security_groups_cache is None else 'exists'}")
            self.logger.debug(f"  - Cache age: {now - self._cache_time if self._cache_time else 'N/A'} seconds")

            # Fetch subnets
            try:
                self.logger.debug("Fetching subnets from /subnet/list...")
                subnets_response = self._make_request("GET", "/subnet/list")
                self.logger.debug(f"Subnets response received (status: {subnets_response.status_code})")
                subnets_data = subnets_response.json()
                self.logger.debug(f"Found {len(subnets_data)} subnets")
                self._subnets_cache = subnets_data
            except Exception as e:
                self.logger.error(f"Failed to fetch subnets: {str(e)}")
                raise SandboxCreationError(f"Failed to fetch subnets: {str(e)}")

            # Fetch security groups
            try:
                self.logger.debug("Fetching security groups from /securitygroup/list...")
                sg_response = self._make_request("GET", "/securitygroup/list")
                self.logger.debug(f"Security groups response received (status: {sg_response.status_code})")
                sg_data = sg_response.json()
                self.logger.debug(f"Found {len(sg_data)} security groups")
                self._security_groups_cache = sg_data
            except Exception as e:
                self.logger.error(f"Failed to fetch security groups: {str(e)}")
                raise SandboxCreationError(f"Failed to fetch security groups: {str(e)}")

            self._cache_time = now
            self.logger.debug("Resource cache updated successfully")
        else:
            self.logger.debug("Using cached resources (still valid)")

        return self._subnets_cache, self._security_groups_cache

    def test_connection(self) -> bool:
        """Test API connection with a simple request."""
        try:
            self.logger.debug("Testing API connection...")
            response = self._make_request("GET", "/compute/list")
            self.logger.debug(f"Connection test successful (status: {response.status_code})")
            return True
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False

    def _generate_sandbox_name(self) -> str:
        """Generate a unique sandbox name."""
        import secrets
        hex_suffix = secrets.token_hex(7)  # 7 bytes = 14 hex chars
        return f"exc-{hex_suffix}"

    def create(
        self,
        name: Optional[str] = None,
        instance_type: str = "n1.2c",
        image_id: int = 7,
        zone_id: int = 1,
    ) -> Sandbox:
        """
        Create a new sandbox.

        Args:
            name: Optional name for the sandbox (auto-generated if not
                  provided, always prefixed with 'exc-')
            instance_type: Instance type (default: n1.2c)
            image_id: Image ID to use (default: 7 for Ubuntu)
            zone_id: Zone ID (default: 1)

        Returns:
            Sandbox object for managing the created instance

        Raises:
            SandboxCreationError: If sandbox creation fails
        """
        if name is None:
            name = self._generate_sandbox_name()
        else:
            # Always prefix with exc- regardless of user input
            if not name.startswith("exc-"):
                name = f"exc-{name}"

        print(f"Creating sandbox: {name}")
        self.logger.debug(f"  Instance type: {instance_type}")
        
        # Get required resources
        subnets, security_groups = self._get_cached_resources()
        self.logger.debug(f"Using subnet: {subnets[0]['name'] if subnets else 'None'}")
        self.logger.debug(f"Using security group: {security_groups[0]['name'] if security_groups else 'None'}")

        if not subnets:
            raise SandboxCreationError(
                "No subnets available. Please create a subnet first."
            )

        if not security_groups:
            raise SandboxCreationError(
                "No security groups available. Please create a security " "group first."
            )

        # Create VM request payload (matching frontend logic)
        request_payload = {
            "allocate_public_ipv4": True,
            "image_id": image_id,
            "instance_type": instance_type,
            "name": name,
            "project_id": 1,
            "ssh_pubkey": "",  # No SSH key needed for programmatic access
            "subnet_id": subnets[0]["id"],  # Use first available subnet
            "zone_id": zone_id,
            "security_group_ids": [security_groups[0]["id"]],  # First sg
        }

        try:
            response = self._make_request(
                "POST", "/compute/create", json=request_payload
            )
            vm_data = response.json()

            # Create Sandbox object
            sandbox = Sandbox(
                client=self,
                vm_id=vm_data["vm_id"],
                name=vm_data["name"],
                instance_type=vm_data["instance_type"],
                public_ipv4=vm_data.get("public_ipv4"),
                state=vm_data["state"],
                zone_id=vm_data["zone_id"],
            )

            self.logger.debug(f"Sandbox created: {sandbox.name} (ID: {sandbox.vm_id})")
            
            # Wait for sandbox to be running
            sandbox._wait_for_running()

            return sandbox

        except Exception as e:
            raise SandboxCreationError(f"Failed to create sandbox: {str(e)}")

    def get_vm_info(self, vm_id: int) -> Dict[str, Any]:
        """Get VM information by ID."""
        try:
            response = self._make_request("GET", "/compute/list")
            vms = response.json()

            for vm in vms:
                if vm.get("vm_id") == vm_id:
                    return vm

            raise ExcloudException(f"VM with ID {vm_id} not found")

        except Exception as e:
            raise ExcloudException(f"Failed to get VM info: {str(e)}")
