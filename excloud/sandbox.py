"""
Sandbox class for managing VM instances and SSH sessions.
"""

import atexit
import signal
import sys
import threading
import time
from typing import TYPE_CHECKING, Optional

import socket
import ssl
import base64
import hashlib
import os
import asyncio
import websockets

# Logging setup
from .logging_config import setup_logger
logger = setup_logger()

from .exceptions import (
    CommandExecutionError,
    ConnectionError,
    SandboxNotFoundError,
    SessionError,
)

if TYPE_CHECKING:
    from .client import Client


class Sandbox:
    """Represents a cloud sandbox (VM instance) with SSH session management."""

    def __init__(
        self,
        client: "Client",
        vm_id: int,
        name: str,
        instance_type: str,
        public_ipv4: Optional[str],
        state: str,
        zone_id: int,
    ):
        """
        Initialize sandbox instance.

        Args:
            client: Excloud client instance
            vm_id: VM ID
            name: Sandbox name
            instance_type: Instance type
            public_ipv4: Public IPv4 address
            state: Current state
            zone_id: Zone ID
        """
        self.client = client
        self.vm_id = vm_id
        self.name = name
        self.instance_type = instance_type
        self.public_ipv4 = public_ipv4
        self.state = state
        self.zone_id = zone_id

        # Session management
        self._session_id: Optional[str] = None
        self._ws: Optional[websocket.WebSocket] = None
        self._session_lock = threading.Lock()
        self._command_lock = threading.Lock()
        self._destroyed = False
        self._last_output = ""
        self._command_complete = threading.Event()
        
        # Event loop management for WebSocket reuse
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._connection_failed = False  # Track if we've had connection failures

        # Register cleanup handlers
        atexit.register(self._cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle process signals for cleanup."""
        self._cleanup()
        sys.exit(0)

    def _cleanup(self):
        """Clean up resources on exit."""
        if not self._destroyed:
            try:
                self.destroy()
            except Exception:
                pass  # Ignore errors during cleanup

    def _wait_for_running(self, timeout: int = 300):
        """Wait for the sandbox to be reachable via ping."""
        import subprocess
        import platform
        
        # Get the public IP once - it's assigned at creation and doesn't change
        vm_info = self.client.get_vm_info(self.vm_id)
        self.public_ipv4 = vm_info.get("public_ipv4")
        
        if not self.public_ipv4:
            raise SessionError("VM created but no public IP assigned")

        logger.debug(f"Pinging {self.public_ipv4} to verify connectivity")
        start_time = time.time()
        
        # Determine ping command based on OS
        if platform.system().lower() == "windows":
            ping_cmd = ["ping", "-n", "1", "-w", "3000", self.public_ipv4]
        else:
            ping_cmd = ["ping", "-c", "1", "-W", "3", self.public_ipv4]

        ping_count = 0
        while time.time() - start_time < timeout:
            try:
                ping_count += 1
                result = subprocess.run(
                    ping_cmd,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                if result.returncode == 0:
                    logger.debug(f"VM reachable via ping (attempt #{ping_count})")
                    return
                else:
                    elapsed = int(time.time() - start_time)
                    logger.debug(f"Ping #{ping_count} failed, retrying... ({elapsed}s elapsed)")
                    time.sleep(3)
                    
            except subprocess.TimeoutExpired:
                logger.debug(f"Ping timeout, retrying...")
                time.sleep(3)
            except Exception as e:
                logger.debug(f"Ping error: {e}, retrying...")
                time.sleep(3)

        raise SessionError(f"VM not reachable via ping after {int(timeout)}s")

    def _create_session(self) -> str:
        """Create a new SSH session and return session ID."""
        if self._destroyed:
            raise SessionError("Cannot create session: sandbox is destroyed")

        try:
            # VM should already be running from client.create()
            # No need to check again here

            # Create session via API
            payload = {
                "vm_id": self.vm_id,
                "user": "ubuntu",  # Default user for Ubuntu images
            }

            response = self.client._make_request(
                "POST", "/compute/instance/connect", json=payload
            )
            session_data = response.json()
            logger.debug(f"Connect API response: {session_data}")

            # Give the server a moment to set up the WebSocket endpoint
            logger.debug("Waiting for WebSocket endpoint to be ready...")
            time.sleep(2)

            return session_data["id"]

        except Exception as e:
            raise SessionError(f"Failed to create SSH session: {str(e)}")

    def _create_websocket_key(self):
        """Generate a random WebSocket key."""
        random_bytes = os.urandom(16)
        return base64.b64encode(random_bytes).decode('ascii')

    def _calculate_accept_key(self, websocket_key):
        """Calculate the expected Sec-WebSocket-Accept value."""
        magic_string = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        accept_key = base64.b64encode(
            hashlib.sha1((websocket_key + magic_string).encode()).digest()
        ).decode('ascii')
        return accept_key

    def _create_websocket_frame(self, message: str) -> bytes:
        """Create a WebSocket text frame."""
        payload = message.encode('utf-8')
        frame = bytearray()

        # First byte: FIN=1, RSV=000, Opcode=0001 (text frame)
        frame.append(0x81)

        # Second byte: MASK=1, Payload length
        payload_length = len(payload)
        if payload_length < 126:
            frame.append(0x80 | payload_length)
        else:
            # For longer payloads, we'd need extended length
            raise ValueError(f"Payload too long for simple frame: {payload_length}")

        # Masking key (4 bytes)
        mask = os.urandom(4)
        frame.extend(mask)

        # Masked payload
        masked_payload = bytearray()
        for i, byte in enumerate(payload):
            masked_payload.append(byte ^ mask[i % 4])
        frame.extend(masked_payload)

        return bytes(frame)

    def _parse_websocket_frame(self, data: bytes) -> str:
        """Parse a WebSocket frame and extract text content."""
        if len(data) < 2:
            return ""

        # Check if it's a text frame
        opcode = data[0] & 0x0F
        if opcode != 0x01:  # Not a text frame
            return ""

        # Get payload length
        payload_len = data[1] & 0x7F
        header_len = 2

        if payload_len < 126:
            # Simple case: payload length fits in 7 bits
            actual_len = payload_len
        elif payload_len == 126:
            # Extended payload length (16-bit)
            if len(data) < 4:
                return ""
            actual_len = int.from_bytes(data[2:4], byteorder='big')
            header_len = 4
        elif payload_len == 127:
            # Extended payload length (64-bit)
            if len(data) < 10:
                return ""
            actual_len = int.from_bytes(data[2:10], byteorder='big')
            header_len = 10
        else:
            return ""

        # Check if we have enough data for the full payload
        if len(data) >= header_len + actual_len:
            try:
                payload_bytes = data[header_len:header_len + actual_len]
                text_payload = payload_bytes.decode('utf-8', errors='replace')
                return text_payload
            except Exception:
                return ""

        return ""

    def _connect_websocket(self, session_id: str):
        """Connect to WebSocket using websocket-client for simplicity and reliability."""
        # Build WebSocket URL (replace http/https with ws/wss)
        if self.client.base_url.startswith("https://"):
            ws_scheme = "wss://"
            base = self.client.base_url[len("https://"):]
        elif self.client.base_url.startswith("http://"):
            ws_scheme = "ws://"
            base = self.client.base_url[len("http://"):]
        else:
            raise ConnectionError(f"Unsupported base URL scheme: {self.client.base_url}")

        ws_url = f"{ws_scheme}{base}/compute/instance/connect/ws/{session_id}"
        print(f"🔗 WebSocket URL: {ws_url}")

        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Prepare headers; keep Host header so server recognizes virtual host
                host_only = base.split('/')[0]
                headers = [
                    f"Host: {host_only}",
                    "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                ]
                # Try normal create_connection first (hostname), then fallback to manual TCP connect
                try:
                    return websocket.create_connection(
                        ws_url,
                        timeout=30,
                        origin="https://console.excloud.in",
                        header=headers,
                        address_family=socket.AF_INET,
                        http_proxy_host=None,
                        http_proxy_port=None,
                        sslopt={"server_hostname": host_only},
                    )
                except Exception as direct_e:
                    print(f"⚠️ Direct create_connection failed: {direct_e}. Attempting manual socket connect...")
                    # Manual socket connect (mimic old code path)
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(30)
                    sock.connect((host_only, 443))
                    return websocket.create_connection(
                        ws_url,
                        timeout=30,
                        origin="https://console.excloud.in",
                        header=headers,
                        sock=sock,
                        sslopt={"server_hostname": host_only},
                    )
            except Exception as e:
                if attempt == max_retries - 1:
                    raise ConnectionError(f"Failed to connect to WebSocket: {e}")
                wait = 2 ** attempt
                print(f"🔄 Retry WebSocket ({attempt+1}/{max_retries}) after {wait}s (IPv4 forced): {e}")
                time.sleep(wait)

        # Should not reach here
        raise ConnectionError("Failed to connect to WebSocket after retries")
        print(f"🔍 Base URL: {self.client.base_url}")
        print(f"🔍 Session ID: {session_id}")

        if self.client.base_url.startswith("https://"):
            host = self.client.base_url.replace("https://", "").split('/')[0]
            port = 443
            use_ssl = True
        else:
            host = self.client.base_url.replace("http://", "").split('/')[0]
            port = 80
            use_ssl = False

        path = f"/compute/instance/connect/ws/{session_id}"

        print(f"🔗 Connecting to WebSocket: {host}:{port}{path}")

        # Retry logic for WebSocket connection
        max_retries = 3
        base_timeout = 30

        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    wait_time = 2 ** attempt
                    print(f"🔄 Retry attempt {attempt + 1}/{max_retries} (waiting {wait_time}s)")
                    time.sleep(wait_time)

                print(f"⏱️  Attempting WebSocket connection with {base_timeout}s timeout...")

                # Create socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(base_timeout)

                # Connect
                print(f"🔗 Connecting to {host}:{port}...")
                sock.connect((host, port))
                print("✅ TCP connection established")

                # Wrap with SSL if needed
                if use_ssl:
                    print("🔒 Starting TLS handshake...")
                    context = ssl.create_default_context()
                    ssl_sock = context.wrap_socket(sock, server_hostname=host)
                    print("✅ TLS handshake completed")
                else:
                    ssl_sock = sock

                # Generate WebSocket key and build handshake
                websocket_key = self._create_websocket_key()
                expected_accept = self._calculate_accept_key(websocket_key)

                request_lines = [
                    f"GET {path} HTTP/1.1",
                    f"Host: {host}",
                    "Upgrade: websocket",
                    "Connection: Upgrade",
                    f"Sec-WebSocket-Key: {websocket_key}",
                    "Sec-WebSocket-Version: 13",
                    "Origin: https://console.excloud.in",
                    "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "",
                    ""
                ]

                request = "\r\n".join(request_lines)
                print("📤 Sending WebSocket handshake...")
                ssl_sock.sendall(request.encode('utf-8'))

                # Read response
                print("📥 Reading handshake response...")
                response_lines = []
                current_line = b""

                while True:
                    byte = ssl_sock.recv(1)
                    if not byte:
                        raise ConnectionError("Connection closed during handshake")

                    current_line += byte
                    if current_line.endswith(b"\r\n"):
                        line = current_line[:-2].decode('utf-8', errors='replace')
                        response_lines.append(line)
                        current_line = b""

                        if line == "":  # Empty line indicates end of headers
                            break

                # Validate handshake response
                if not response_lines:
                    raise ConnectionError("No handshake response received")

                status_line = response_lines[0]
                if "101" not in status_line:
                    raise ConnectionError(f"WebSocket handshake failed: {status_line}")

                # Parse headers
                headers = {}
                for line in response_lines[1:]:
                    if line and ":" in line:
                        key, value = line.split(":", 1)
                        headers[key.strip().lower()] = value.strip()

                # Verify WebSocket accept key
                if "sec-websocket-accept" not in headers:
                    raise ConnectionError("Missing Sec-WebSocket-Accept header")

                if headers["sec-websocket-accept"] != expected_accept:
                    raise ConnectionError("Invalid Sec-WebSocket-Accept header")

                print("✅ WebSocket handshake successful")
                return ssl_sock

            except socket.timeout:
                print(f"⏰ Connection timeout on attempt {attempt + 1}")
                if attempt == max_retries - 1:
                    raise ConnectionError(f"WebSocket connection timed out after {max_retries} attempts")
            except Exception as e:
                print(f"❌ Connection error on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise ConnectionError(f"Failed to connect to WebSocket: {str(e)}")

        raise ConnectionError("Failed to connect to WebSocket: maximum retries exceeded")

    def _ensure_session(self):
        """Ensure we have an active WebSocket session."""
        with self._session_lock:
            if self._destroyed:
                raise SessionError("Cannot ensure session: sandbox is destroyed")

            # Check if we need a new session
            if self._session_id is None or self._ws is None:
                self._session_id = self._create_session()
                self._ws = self._connect_websocket(self._session_id)

            # Test connection
            try:
                # For websocket-client, use .connected attribute; for raw socket, use getpeername()
                if hasattr(self._ws, 'connected'):
                    if not self._ws.connected:
                        raise Exception("WebSocket not connected")
                elif hasattr(self._ws, 'getpeername'):
                    self._ws.getpeername()
                else:
                    # Unknown socket object; assume ok
                    pass
            except Exception as e:
                print(f"🔄 Session test failed ({str(e)}), creating new session...")
                # Connection is dead, create new session
                try:
                    self._ws.close()
                except Exception:
                    pass

                self._session_id = self._create_session()
                self._ws = self._connect_websocket(self._session_id)

    def _execute_command(self, command: str, timeout: int = 30) -> str:
        """Execute a command via WebSocket and return output."""
        print(f"🎯 Executing command: {command}")
        self._ensure_session()

        try:
            # Verify WebSocket is still connected
            if not self._ws:
                raise ConnectionError("WebSocket is not connected")

            # Send command using WebSocket frame
            command_with_newline = command + "\n"
            print(f"📤 Sending command: {repr(command_with_newline)}")

            try:
                frame = self._create_websocket_frame(command_with_newline)
                self._ws.send(frame)
                print("✅ Command sent successfully")
            except Exception as send_error:
                print(f"❌ Failed to send command: {send_error}")
                # Try to reconnect and resend
                self._session_id = None
                self._ws = None
                self._ensure_session()
                frame = self._create_websocket_frame(command_with_newline)
                self._ws.send(frame)
                print("✅ Command sent after reconnection")

            # Read output with timeout
            start_time = time.time()
            output_parts = []
            print(f"📥 Reading output with {timeout}s timeout...")

            # Buffer for incomplete WebSocket frames
            frame_buffer = b""
            no_data_count = 0

            while time.time() - start_time < timeout:
                try:
                    # Set a short timeout for receiving messages
                    self._ws.settimeout(1.0)
                    raw_data = self._ws.recv(4096)

                    if not raw_data:
                        no_data_count += 1
                        if no_data_count >= 3:  # No data for 3 consecutive attempts
                            break
                        continue

                    no_data_count = 0
                    frame_buffer += raw_data

                    # Try to parse complete frames from buffer
                    while len(frame_buffer) >= 2:
                        # Check payload length to see if we have a complete frame
                        payload_len = frame_buffer[1] & 0x7F
                        header_len = 2
                        actual_len = payload_len

                        if payload_len == 126:
                            if len(frame_buffer) < 4:
                                break  # Need more data
                            actual_len = int.from_bytes(frame_buffer[2:4], byteorder='big')
                            header_len = 4
                        elif payload_len == 127:
                            if len(frame_buffer) < 10:
                                break  # Need more data
                            actual_len = int.from_bytes(frame_buffer[2:10], byteorder='big')
                            header_len = 10

                        total_frame_len = header_len + actual_len

                        if len(frame_buffer) >= total_frame_len:
                            # We have a complete frame
                            complete_frame = frame_buffer[:total_frame_len]
                            frame_buffer = frame_buffer[total_frame_len:]

                            message = self._parse_websocket_frame(complete_frame)
                            if message:
                                print(f"📨 Received: {repr(message[:100])}{'...' if len(message) > 100 else ''}")
                                output_parts.append(message)

                                # Check if we see a prompt pattern indicating command completion
                                full_output = "".join(output_parts)
                                if ("$ " in full_output or "# " in full_output) and len(output_parts) > 1:
                                    print("🎯 Command completion detected")
                                    break
                        else:
                            # Frame is incomplete, wait for more data
                            break

                except socket.timeout:
                    # No more data available, but check if we have some output
                    if output_parts:
                        print(f"⏰ Timeout but got {len(output_parts)} message parts")
                        break
                    continue
                except Exception as e:
                    # Connection error, try to reconnect
                    self._session_id = None
                    self._ws = None
                    raise ConnectionError(f"WebSocket error: {str(e)}")

            # Join all output parts
            full_output = "".join(output_parts)
            print(f"📊 Full raw output: {repr(full_output)}")

            # Minimal cleanup - just remove command echo and prompts
            lines = full_output.split("\n")
            cleaned_lines = []

            command_stripped = command.strip()
            for line in lines:
                line_stripped = line.strip()
                # Skip empty lines, command echo, and shell prompts
                if (line_stripped and
                    line_stripped != command_stripped and
                    not line_stripped.endswith("$ ") and
                    not line_stripped.endswith("# ") and
                    not line_stripped.startswith("$ ") and
                    not line_stripped.startswith("# ")):
                    cleaned_lines.append(line_stripped)

            result = "\n".join(cleaned_lines)
            print(f"📋 Cleaned result: {repr(result)}")
            return result

        except Exception as e:
            raise CommandExecutionError(f"Failed to execute command: {str(e)}")

    def _execute_command_lib(self, command: str, timeout: int = 30) -> str:
        """Execute a command in the sandbox using websocket-client."""
        print(f"🎯 Executing command: {command}")
        self._ensure_session()

        try:
            if not self._ws:
                raise ConnectionError("WebSocket is not connected")

            command_with_newline = command + "\n"
            print(f"📤 Sending command: {repr(command_with_newline)}")
            self._ws.send(command_with_newline)
            print("✅ Command sent successfully")

            start_time = time.time()
            output_parts = []
            print(f"📥 Reading output with {timeout}s timeout...")

            while time.time() - start_time < timeout:
                try:
                    self._ws.settimeout(1.0)
                    message = self._ws.recv()
                    if not message:
                        continue

                    print(f"📨 Received: {repr(message[:100])}{'...' if len(message) > 100 else ''}")
                    output_parts.append(message)

                    # Detect shell prompt indicating completion
                    if ("$ " in message or "# " in message):
                        break
                except websocket.WebSocketTimeoutException:
                    # Allow loop to continue until overall timeout
                    continue
                except Exception as e:
                    self._session_id = None
                    self._ws = None
                    raise ConnectionError(f"WebSocket error: {e}")

            full_output = "".join(output_parts)
            print(f"📊 Full raw output: {repr(full_output)}")

            # Basic cleanup similar to previous implementation
            lines = full_output.split("\n")
            cleaned_lines = []
            command_stripped = command.strip()
            for line in lines:
                line_stripped = line.strip()
                if (
                    line_stripped
                    and line_stripped != command_stripped
                    and not line_stripped.endswith("$ ")
                    and not line_stripped.endswith("# ")
                    and not line_stripped.startswith("$ ")
                    and not line_stripped.startswith("# ")
                ):
                    cleaned_lines.append(line_stripped)

            result = "\n".join(cleaned_lines)
            print(f"📋 Cleaned result: {repr(result)}")
            return result

        except Exception as e:
            raise CommandExecutionError(f"Failed to execute command: {str(e)}")

    async def _wait_for_shell_ready(self, ws, timeout: int = 30):
        """Wait for the initial shell welcome message and prompt to complete."""
        logger.debug("Waiting for shell to be ready...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                msg_raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                if isinstance(msg_raw, bytes):
                    msg = msg_raw.decode("utf-8", errors="replace")
                else:
                    msg = msg_raw
                
                logger.debug(f"Shell init: {repr(msg[:50])}{'...' if len(msg) > 50 else ''}")
                
                # Look for shell prompt indicating readiness
                if ("$ " in msg or "# " in msg) and ("@" in msg or "root" in msg):
                    logger.debug("Shell is ready")
                    return
                    
            except asyncio.TimeoutError:
                continue
                
        logger.debug("Shell readiness timeout, proceeding anyway")

    async def _ensure_websocket_connection(self):
        """Ensure we have a valid WebSocket connection."""
        if self._ws is None or getattr(self._ws, 'close_code', None) is not None:
            logger.debug("Creating new WebSocket connection")
            
            # Only check VM state if we've had connection failures before
            # This avoids unnecessary API calls for normal operation
            if self._connection_failed:
                logger.debug("Previous connection failed, checking VM state...")
                try:
                    vm_info = self.client.get_vm_info(self.vm_id)
                    vm_state = vm_info.get("state", "UNKNOWN")
                    if vm_state in ["TERMINATED", "STOPPED", "FAILED"]:
                        raise ConnectionError(f"Cannot connect to WebSocket: VM is in {vm_state} state. VM may have been shut down.")
                    logger.debug(f"VM state is {vm_state}, proceeding with connection")
                except Exception as e:
                    # If we can't get VM info, continue anyway - might be a temporary API issue
                    logger.debug(f"Could not check VM state: {e}, proceeding anyway")
                
            session_id = self._create_session()
            # Build WebSocket URL
            if self.client.base_url.startswith("https://"):
                ws_scheme = "wss://"
                base = self.client.base_url[len("https://"):]
            elif self.client.base_url.startswith("http://"):
                ws_scheme = "ws://"
                base = self.client.base_url[len("http://"):]
            else:
                raise ConnectionError(f"Unsupported base URL scheme: {self.client.base_url}")
            ws_url = f"{ws_scheme}{base}/compute/instance/connect/ws/{session_id}"

            # Retry WebSocket connection with exponential backoff
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    # Add some delay between retries
                    if attempt > 0:
                        wait_time = 2 ** attempt
                        await asyncio.sleep(wait_time)
                    
                    # Establish new websocket connection
                    self._ws = await websockets.connect(
                        ws_url,
                        origin="https://console.excloud.in",
                        ping_interval=None,
                        open_timeout=30,
                        family=socket.AF_INET,
                        compression=None,
                    )
                    
                    # Wait for shell to be ready before proceeding
                    await self._wait_for_shell_ready(self._ws)
                    self._connection_failed = False  # Reset flag on successful connection
                    return  # Success
                    
                except (ConnectionResetError, ConnectionRefusedError, OSError) as e:
                    self._connection_failed = True
                    if attempt == max_retries - 1:
                        raise ConnectionError(f"Failed to establish WebSocket connection after {max_retries} attempts. VM may be shut down or unreachable: {e}")
                except websockets.exceptions.ConnectionClosedError as e:
                    self._connection_failed = True
                    if attempt == max_retries - 1:
                        raise ConnectionError(f"WebSocket connection closed immediately. VM appears to be shut down or SSH service is not running: {e}")
                except Exception as e:
                    self._connection_failed = True
                    if attempt == max_retries - 1:
                        raise ConnectionError(f"Failed to establish WebSocket connection. VM may be shut down: {e}")

    async def _execute_command_ws(self, command: str, timeout: int = 30) -> str:
        """Execute a command using the `websockets` asyncio library."""
        logger.debug(f"Executing command: {command}")
        
        # Warn about potentially destructive commands
        shutdown_commands = ["shutdown", "poweroff", "halt", "reboot", "init 0", "init 6"]
        if any(cmd in command.lower() for cmd in shutdown_commands):
            logger.warning(f"⚠️ Command '{command}' may shut down the VM. Subsequent commands will fail.")
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                # Ensure we have a valid WebSocket connection
                await self._ensure_websocket_connection()
                
                ws = self._ws
                # Try to send command
                logger.debug(f"Sending command to WebSocket: {repr(command + '\n')}")
                await ws.send(command + "\n")

                output_parts = []
                end_time = time.time() + timeout
                
                while time.time() < end_time:
                    try:
                        msg_raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        if isinstance(msg_raw, bytes):
                            msg = msg_raw.decode("utf-8", errors="replace")
                        else:
                            msg = msg_raw
                        
                        if msg:
                            logger.debug(f"Received WebSocket message: {repr(msg[:100])}{'...' if len(msg) > 100 else ''}")
                            output_parts.append(msg)
                            # Detect shell prompt indicating completion
                            if ("$ " in msg or "# " in msg):
                                logger.debug("Command completion detected (shell prompt found)")
                                break
                    except asyncio.TimeoutError:
                        continue
                    except websockets.exceptions.ConnectionClosed as e:
                        # Mark WebSocket as invalid so it gets recreated next time
                        self._ws = None
                        self._connection_failed = True
                        if not output_parts:
                            if attempt == max_retries - 1:
                                raise ConnectionError(f"WebSocket connection closed during command execution: {e}")
                            break  # Try again with new connection
                        else:
                            # Got partial output, return it with warning
                            logger.warning(f"⚠️ Connection lost mid-command, returning partial output")
                            break

                if output_parts:  # Got some output, process it
                    full_output = "".join(output_parts)
                    logger.debug(f"Raw command output: {repr(full_output)}")
                    result = self._clean_command_output(full_output, command)
                    logger.debug(f"Cleaned command result: {repr(result)}")
                    return result
                
                # No output received, retry if attempts left
                if attempt < max_retries - 1:
                    self._ws = None  # Force reconnection
                    continue
                else:
                    raise ConnectionError("No output received after all attempts")
                    
            except (websockets.exceptions.ConnectionClosed, ConnectionResetError, BrokenPipeError) as e:
                # Connection error during send - mark as invalid and retry
                self._ws = None
                self._connection_failed = True
                if attempt == max_retries - 1:
                    raise ConnectionError(f"Failed to send command after {max_retries} attempts: {e}")
                continue  # Retry
                
            except Exception as e:
                # Mark WebSocket as invalid so it gets recreated next time
                self._ws = None
                if attempt == max_retries - 1:
                    error_msg = str(e)
                    if "VM is in" in error_msg and ("TERMINATED" in error_msg or "STOPPED" in error_msg):
                        raise CommandExecutionError(f"Cannot execute command: {error_msg}")
                    elif "WebSocket connection closed immediately" in error_msg:
                        raise CommandExecutionError(f"Cannot execute command: VM appears to be shut down or unreachable")
                    else:
                        raise CommandExecutionError(f"Failed to execute command after {max_retries} attempts: {error_msg}")
                continue  # Retry
                
        raise CommandExecutionError("Command execution failed after all retry attempts")

        

    def _clean_command_output(self, raw_output: str, command: str) -> str:
        """Clean up command output by removing ANSI codes, prompts, and command echo."""
        import re
        
        # Remove ANSI escape sequences
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        cleaned = ansi_escape.sub('', raw_output)
        
        # Remove carriage returns and normalize line endings
        cleaned = cleaned.replace('\r\n', '\n').replace('\r', '\n')
        
        # Split into lines and process
        lines = cleaned.split('\n')
        result_lines = []
        command_stripped = command.strip()
        
        # Find the command echo and extract output after it
        command_found = False
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            
            # Look for the command echo
            if line_stripped == command_stripped:
                command_found = True
                # Collect lines after the command until we hit a prompt
                for j in range(i + 1, len(lines)):
                    output_line = lines[j].strip()
                    
                    # Stop at shell prompt
                    if (output_line.endswith('$ ') or 
                        output_line.endswith('# ') or
                        ('@' in output_line and ':~$' in output_line) or
                        ('@' in output_line and output_line.endswith('$'))):
                        break
                    
                    # Skip empty lines and control sequences
                    if output_line and not output_line.startswith('?2004'):
                        result_lines.append(output_line)
                break
        
        # If we didn't find the command echo, try to extract meaningful output
        if not command_found:
            for line in lines:
                line_stripped = line.strip()
                # Skip empty lines, prompts, and control sequences
                if (line_stripped and 
                    not line_stripped.endswith('$ ') and
                    not line_stripped.endswith('# ') and
                    not ('@' in line_stripped and ':~$' in line_stripped) and
                    not line_stripped.startswith('?2004') and
                    line_stripped != command_stripped):
                    result_lines.append(line_stripped)
        
        return '\n'.join(result_lines)

    def _ensure_event_loop(self):
        """Ensure we have a running event loop in a background thread."""
        if self._loop is None or self._loop.is_closed():
            # Create a new event loop in a background thread
            def run_loop():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._loop.run_forever()
            
            self._loop_thread = threading.Thread(target=run_loop, daemon=True)
            self._loop_thread.start()
            
            # Wait a bit for the loop to start
            time.sleep(0.1)

    def run(self, command: str, timeout: int = 30) -> str:
        """
        Execute a command in the sandbox.

        Args:
            command: Command to execute
            timeout: Timeout in seconds (default: 30)

        Returns:
            Command output as string

        Raises:
            CommandExecutionError: If command execution fails
            SessionError: If session management fails
            ConnectionError: If WebSocket connection fails
        """
        if self._destroyed:
            raise SessionError("Cannot run command: sandbox is destroyed")

        debug_mode = os.getenv("EXCLOUD_DEBUG") == "1"

        with self._command_lock:
            self._ensure_event_loop()
            
            # Run the async command in the persistent event loop
            future = asyncio.run_coroutine_threadsafe(
                self._execute_command_ws(command, timeout), 
                self._loop
            )
            try:
                return future.result(timeout + 5)  # Add buffer to timeout
            except TimeoutError:
                # Cancel the pending task to avoid hanging
                future.cancel()
                if debug_mode:
                    raise
                raise CommandExecutionError(f"Command '{command}' timed out after {timeout}s. VM may be unreachable or shut down.")
            except Exception as e:
                # In debug mode, show full traceback
                if debug_mode:
                    raise
                
                # In normal mode, show clean error message
                if isinstance(e, (CommandExecutionError, SessionError, ConnectionError)):
                    # These are already user-friendly, just re-raise
                    raise
                else:
                    # Convert other exceptions to user-friendly messages
                    raise CommandExecutionError(f"Command '{command}' failed: {str(e)}")

    def destroy(self):
        """Destroy the sandbox and clean up all resources."""
        if self._destroyed:
            return

        self._destroyed = True

        # Close WebSocket connection
        if self._ws:
            try:
                if self._loop and not self._loop.is_closed():
                    # Close WebSocket in the same event loop it was created in
                    future = asyncio.run_coroutine_threadsafe(
                        self._ws.close(), self._loop
                    )
                    future.result(timeout=5)
                else:
                    # Fallback for when loop is not available
                    close_coro = self._ws.close()
                    if asyncio.iscoroutine(close_coro):
                        try:
                            asyncio.run(close_coro)
                        except RuntimeError:
                            pass
            except Exception:
                pass
            self._ws = None

        # Stop the event loop
        if self._loop and not self._loop.is_closed():
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
                if self._loop_thread and self._loop_thread.is_alive():
                    self._loop_thread.join(timeout=2)
            except Exception:
                pass
            self._loop = None
            self._loop_thread = None

        self._session_id = None

        # Terminate the VM
        try:
            payload = {"vm_id": self.vm_id}
            self.client._make_request("POST", "/compute/terminate", json=payload)
        except Exception as e:
            # Log error but don't raise - cleanup should be best effort
            print(f"Warning: Failed to terminate VM {self.vm_id}: {str(e)}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures cleanup."""
        self.destroy()

    def __del__(self):
        """Destructor - ensures cleanup."""
        self._cleanup()

    def __repr__(self):
        return (
            f"Sandbox(vm_id={self.vm_id}, name='{self.name}', " f"state='{self.state}')"
        )
