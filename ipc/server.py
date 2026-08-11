"""
AirOS IPC Server
WebSocket server for communication between Python engine and Electron UI.

Architecture:
- Engine sends telemetry at 10 Hz (100ms interval)
- UI sends control commands as JSON
- Server runs in a SEPARATE THREAD from the real-time engine
- The engine is NEVER blocked by IPC activity

Protocol:
  Engine → UI: {"type": "telemetry", ...}
  UI → Engine: {"type": "control", "command": "start"|"stop"|"pause"|"resume"|"calibrate"}
"""

import asyncio
import json
import logging
import threading
import time
from typing import Optional, Set, Callable

try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False

logger = logging.getLogger(__name__)

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 7890


class IPCServer:
    """
    WebSocket IPC server.
    Runs on a background asyncio event loop in a dedicated thread.
    Thread-safe — telemetry can be pushed from any thread.
    """

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        on_command: Optional[Callable[[str, dict], None]] = None,
    ):
        self._host = host
        self._port = port
        self._on_command = on_command
        self._clients: Set = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server = None
        self._serve_task = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_telemetry: Optional[dict] = None
        self._telemetry_lock = threading.Lock()

    def start(self):
        """Start the IPC server in a background thread."""
        if not WEBSOCKETS_AVAILABLE:
            logger.warning("websockets not available — IPC disabled")
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="IPCServer"
        )
        self._thread.start()
        logger.info(f"IPC server starting on ws://{self._host}:{self._port}")

    def _run_loop(self):
        """Run the asyncio event loop in this thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._serve_task = self._loop.create_task(self._serve())
        try:
            self._loop.run_forever()
        finally:
            # Cancel pending tasks BEFORE closing the loop so that
            # async context managers (e.g. websockets.serve) exit cleanly.
            try:
                pending = asyncio.all_tasks(self._loop)
                for task in pending:
                    task.cancel()
                if pending:
                    self._loop.run_until_complete(
                        asyncio.gather(*pending, return_exceptions=True)
                    )
            except Exception:
                pass
            self._loop.close()

    async def _serve(self):
        """Main asyncio server coroutine."""
        try:
            async with websockets.serve(
                self._handle_client,
                self._host,
                self._port,
                ping_interval=None,  # Disable keepalive — we control this
                max_size=None,
            ) as server:
                self._server = server
                logger.info(f"IPC WebSocket server listening on ws://{self._host}:{self._port}")
                while self._running:
                    await asyncio.sleep(0.1)
        except OSError as e:
            logger.error(f"IPC server failed to start: {e}")

    async def _handle_client(self, websocket, path=None):
        """Handle a connected client (UI)."""
        client_id = id(websocket)
        self._clients.add(websocket)
        logger.info(f"UI connected (id={client_id}, total={len(self._clients)})")

        try:
            # Send current telemetry immediately on connect
            with self._telemetry_lock:
                if self._last_telemetry:
                    await websocket.send(json.dumps(self._last_telemetry))

            async for message in websocket:
                await self._handle_message(message, websocket)

        except Exception as e:
            logger.debug(f"Client {client_id} disconnected: {e}")
        finally:
            self._clients.discard(websocket)
            logger.info(f"UI disconnected (id={client_id}, remaining={len(self._clients)})")

    async def _handle_message(self, message: str, websocket):
        """Handle an incoming message from the UI."""
        try:
            data = json.loads(message)
            msg_type = data.get("type", "")

            if msg_type == "control":
                command = data.get("command", "")
                logger.info(f"Received command: {command}")
                if self._on_command:
                    self._on_command(command, data)
            else:
                logger.debug(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON from UI: {e}")

    def push_telemetry(self, telemetry_dict: dict):
        """
        Send telemetry to all connected clients.
        Thread-safe — can be called from the engine thread.
        """
        self.push_message(telemetry_dict)

    def push_message(self, message: dict):
        """
        Send an arbitrary JSON-serializable message to all connected clients.
        Thread-safe — can be called from any thread.
        """
        payload = json.dumps(message)
        with self._telemetry_lock:
            self._last_telemetry = message

        if not self._clients or self._loop is None:
            return

        # Schedule the send on the IPC event loop (non-blocking from engine thread)
        asyncio.run_coroutine_threadsafe(
            self._broadcast(payload),
            self._loop,
        )

    async def _broadcast(self, message: str):
        """Send a message to all connected clients."""
        if not self._clients:
            return
        # Create a copy to avoid mutation during iteration
        clients = set(self._clients)
        disconnected = set()
        for client in clients:
            try:
                await client.send(message)
            except Exception:
                disconnected.add(client)
        self._clients -= disconnected

    def stop(self):
        """Stop the IPC server gracefully. Blocks until the server thread exits."""
        self._running = False
        if self._loop:
            # Stop the run_forever loop from a different thread.
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("IPC server stopped")
