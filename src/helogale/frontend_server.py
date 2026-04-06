#!/usr/bin/env python
"""
Simple frontend server for the packet analyzer.
Exposes analyzer state, events, and alerts via a REST API.
Can be wrapped by a web framework (FastAPI, Flask) or used directly with websockets.
"""

import asyncio
import json
import threading
from collections import deque
from typing import Callable, Iterable


class FrontendBridge:
    """
    Bridge between PacketAnalyzer and frontend clients.
    Manages event subscriptions, buffering, and state queries.
    """

    def __init__(self, analyzer, max_buffered_events: int = 1000):
        self.analyzer = analyzer
        self.max_buffered_events = max_buffered_events
        self._lock = threading.Lock()
        self._subscribers: dict[str, Callable[[dict], None]] = {}
        self._event_buffer: deque[dict] = deque(maxlen=max_buffered_events)
        self._subscription_id_counter = 0

        # Register ourselves as a listener to the analyzer
        self.analyzer.add_event_listener(self._on_analyzer_event)

    def _on_analyzer_event(self, event: dict) -> None:
        """Called by the analyzer whenever a new event is emitted."""
        with self._lock:
            self._event_buffer.append(event)
            # Notify all subscribers of the new event
            for subscriber in list(self._subscribers.values()):
                try:
                    subscriber(event)
                except Exception as e:
                    print(f"Error in subscriber: {e}")

    def subscribe(self, on_event: Callable[[dict], None]) -> str:
        """
        Register a subscriber callback for new events.
        Returns a subscription ID that can be used to unsubscribe.
        """
        with self._lock:
            sub_id = str(self._subscription_id_counter)
            self._subscription_id_counter += 1
            self._subscribers[sub_id] = on_event
        return sub_id

    def unsubscribe(self, sub_id: str) -> None:
        with self._lock:
            self._subscribers.pop(sub_id, None)

    def get_state(self) -> dict:
        """Return the current analyzer state snapshot."""
        return self.analyzer.get_state_snapshot()

    def get_recent_events(self, limit: int = 100) -> list[dict]:
        """Fetch recent events (with optional limit)."""
        return self.analyzer.get_recent_events(limit)

    def get_recent_alerts(self, limit: int = 50) -> list[dict]:
        """Fetch recent alerts (with optional limit)."""
        return self.analyzer.get_recent_alerts(limit)

    def get_buffered_events_since(self, since_id: int | None = None) -> list[dict]:
        """
        Fetch all buffered events since a given event ID.
        If since_id is None, return all buffered events.
        """
        with self._lock:
            if since_id is None:
                return list(self._event_buffer)
            return [e for e in self._event_buffer if e.get("id", 0) > since_id]

    def stop_analyzer(self) -> None:
        """Stop the analyzer gracefully."""
        self.analyzer.stop()


class SimpleWebSocketServer:
    """
    Simple WebSocket server for pushing analyzer events to clients.
    For production, consider FastAPI's WebSocketException or Starlette.
    """

    def __init__(self, bridge: FrontendBridge, host: str = "localhost", port: int = 8765):
        self.bridge = bridge
        self.host = host
        self.port = port
        self._clients: set[asyncio.StreamWriter] = set()

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        addr = writer.get_extra_info("peername")
        print(f"Client connected: {addr}")
        self._clients.add(writer)

        try:
            # Send current state to the client
            state = self.bridge.get_state()
            await self._send_json(writer, {"type": "state", "payload": state})

            while True:
                # Simple line-based protocol: commands are JSON objects
                data = await reader.readline()
                if not data:
                    break

                try:
                    command = json.loads(data.decode().strip())
                    await self._handle_command(writer, command)
                except json.JSONDecodeError:
                    await self._send_json(writer, {"type": "error", "message": "Invalid JSON"})
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Error handling client {addr}: {e}")
        finally:
            self._clients.discard(writer)
            writer.close()
            await writer.wait_closed()
            print(f"Client disconnected: {addr}")

    async def _handle_command(self, writer: asyncio.StreamWriter, command: dict) -> None:
        cmd_type = command.get("type")

        if cmd_type == "get_state":
            state = self.bridge.get_state()
            await self._send_json(writer, {"type": "state", "payload": state})

        elif cmd_type == "get_recent_events":
            limit = command.get("limit", 100)
            events = self.bridge.get_recent_events(limit)
            await self._send_json(writer, {"type": "events", "payload": events})

        elif cmd_type == "get_recent_alerts":
            limit = command.get("limit", 50)
            alerts = self.bridge.get_recent_alerts(limit)
            await self._send_json(writer, {"type": "alerts", "payload": alerts})

        elif cmd_type == "subscribe":
            # Client subscribes to new events
            sub_id = self.bridge.subscribe(lambda evt: asyncio.run_coroutine_threadsafe(
                self._send_json(writer, {"type": "event", "payload": evt}),
                asyncio.get_event_loop()
            ))
            await self._send_json(writer, {"type": "subscribed", "sub_id": sub_id})

        elif cmd_type == "stop":
            self.bridge.stop_analyzer()
            await self._send_json(writer, {"type": "stopped"})

        else:
            await self._send_json(writer, {"type": "error", "message": f"Unknown command: {cmd_type}"})

    async def _send_json(self, writer: asyncio.StreamWriter, data: dict) -> None:
        message = json.dumps(data) + "\n"
        writer.write(message.encode())
        await writer.drain()

    async def start(self) -> None:
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        print(f"WebSocket server listening on ws://{self.host}:{self.port}")
        async with server:
            await server.serve_forever()


class SimpleHTTPServer:
    """
    Simple REST API server for the analyzer (no external dependencies).
    Returns JSON responses for state, events, and alerts queries.
    For production, use FastAPI or Flask.
    """

    def __init__(self, bridge: FrontendBridge, host: str = "localhost", port: int = 8080):
        self.bridge = bridge
        self.host = host
        self.port = port

    def _parse_request(self, data: str) -> tuple[str, str, dict]:
        """Parse a simple HTTP request. Returns (method, path, query_params)."""
        lines = data.split("\r\n")
        if not lines:
            return "", "", {}

        request_line = lines[0].split()
        if len(request_line) < 2:
            return "", "", {}

        method, path = request_line[0], request_line[1]

        # Extract query params
        if "?" in path:
            path, query_string = path.split("?", 1)
            query_params = {}
            for pair in query_string.split("&"):
                if "=" in pair:
                    k, v = pair.split("=", 1)
                    query_params[k] = v
        else:
            query_params = {}

        return method, path, query_params

    def _format_response(self, status: int, body: dict) -> str:
        """Format a simple HTTP JSON response."""
        json_body = json.dumps(body)
        return (
            f"HTTP/1.1 {status} OK\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(json_body)}\r\n"
            f"Access-Control-Allow-Origin: *\r\n"
            f"\r\n"
            f"{json_body}"
        )

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        addr = writer.get_extra_info("peername")
        try:
            data = await asyncio.wait_for(reader.read(4096), timeout=5.0)
            request = data.decode().strip()

            if not request:
                writer.close()
                return

            method, path, query_params = self._parse_request(request)

            # Route requests
            if path == "/api/state" and method == "GET":
                state = self.bridge.get_state()
                response = self._format_response(200, {"status": "ok", "data": state})
            elif path == "/api/events" and method == "GET":
                limit = int(query_params.get("limit", 100))
                events = self.bridge.get_recent_events(limit)
                response = self._format_response(200, {"status": "ok", "data": events})
            elif path == "/api/alerts" and method == "GET":
                limit = int(query_params.get("limit", 50))
                alerts = self.bridge.get_recent_alerts(limit)
                response = self._format_response(200, {"status": "ok", "data": alerts})
            elif path == "/api/stop" and method == "POST":
                self.bridge.stop_analyzer()
                response = self._format_response(200, {"status": "ok", "message": "Analyzer stopped"})
            else:
                response = self._format_response(404, {"status": "error", "message": "Not found"})

            writer.write(response.encode())
            await writer.drain()
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            print(f"Error handling client {addr}: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def start(self) -> None:
        server = await asyncio.start_server(self.handle_client, self.host, self.port)
        print(f"HTTP server listening on http://{self.host}:{self.port}")
        async with server:
            await server.serve_forever()


if __name__ == "__main__":
    # Example usage:
    # from packet_analyzer import PacketAnalyzer, ensure_root
    # 
    # ensure_root()
    # analyzer = PacketAnalyzer(
    #     iface="wlan0",
    #     home_ssid="MyNetwork",
    #     expected_bssids=["aa:bb:cc:dd:ee:ff"],
    # )
    # 
    # bridge = FrontendBridge(analyzer)
    # 
    # # Start HTTP and WebSocket servers
    # async def main():
    #     await asyncio.gather(
    #         SimpleHTTPServer(bridge, port=8080).start(),
    #         SimpleWebSocketServer(bridge, port=8765).start(),
    #     )
    # 
    # asyncio.run(main())
    print("FrontendBridge and server classes ready for use")
