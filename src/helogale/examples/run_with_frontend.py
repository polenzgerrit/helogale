#!/usr/bin/env python
"""
Example: Run the packet analyzer with a simple HTTP/WebSocket server for frontend monitoring.

Usage:
    sudo python -m helogale.examples.run_with_frontend \
        --iface wlan0 \
        --ssid "MyNetwork" \
        --expected-bssid "aa:bb:cc:dd:ee:ff" \
        --http-port 8080 \
        --ws-port 8765
"""

import argparse
import asyncio
import signal
import sys
import threading
from typing import Optional

# These imports assume the module is run as a package or PYTHONPATH is set
from helogale.packet_analyzer import PacketAnalyzer, ensure_root
from helogale.frontend_server import FrontendBridge, SimpleHTTPServer, SimpleWebSocketServer


async def run_services(bridge, http_port: int = 8080, ws_port: int = 8765):
    """Run both HTTP and WebSocket servers concurrently."""
    http_server = SimpleHTTPServer(bridge, host="0.0.0.0", port=http_port)
    ws_server = SimpleWebSocketServer(bridge, host="0.0.0.0", port=ws_port)

    http_task = asyncio.create_task(http_server.start())
    ws_task = asyncio.create_task(ws_server.start())

    try:
        await asyncio.gather(http_task, ws_task)
    except KeyboardInterrupt:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Run packet analyzer with frontend bridge for HTTP/WS monitoring"
    )
    parser.add_argument("--iface", default="wlan0", help="Monitor-mode interface to use")
    parser.add_argument("--ssid", required=True, help="Home SSID to monitor")
    parser.add_argument(
        "--expected-bssid", action="append", default=[], help="Expected AP BSSID for the home network"
    )
    parser.add_argument("--expected-count", type=int, help="Expected number of APs broadcasting the home SSID")
    parser.add_argument(
        "--deauth-threshold", type=int, default=5,
        help="Number of deauths in the deauth-window that triggers an alert"
    )
    parser.add_argument(
        "--deauth-window", type=int, default=10, help="Window in seconds for deauth spike detection"
    )
    parser.add_argument(
        "--rogue-tolerance", type=int, default=0,
        help="Allowed extra BSSIDs beyond the expected count before alerting"
    )
    parser.add_argument(
        "--beacon-retention", type=int, default=60,
        help="Seconds of beacon history to retain for SSID tracking"
    )
    parser.add_argument(
        "--channels", help="Comma-separated channels to hop through, default all channels"
    )
    parser.add_argument(
        "--hop-interval", type=float, default=5.0, help="Seconds to stay on each channel while hopping"
    )
    parser.add_argument("--http-port", type=int, default=8080, help="HTTP API port")
    parser.add_argument("--ws-port", type=int, default=8765, help="WebSocket server port")

    args = parser.parse_args()

    # Ensure we have root privileges
    ensure_root()

    # Parse channels
    if args.channels is not None:
        channels = [int(c.strip()) for c in args.channels.split(",") if c.strip()]
    else:
        channels = list(range(1, 14))

    print(f"\n{'='*70}")
    print("Helogale Packet Analyzer + Frontend Server")
    print(f"{'='*70}")
    print(f"Interface: {args.iface}")
    print(f"SSID: {args.ssid}")
    print(f"Channels: {channels}")
    print(f"Hop interval: {args.hop_interval}s")
    print(f"Expected BSSIDs: {args.expected_bssid or 'None'}")
    print(f"HTTP API: http://0.0.0.0:{args.http_port}")
    print(f"WebSocket: ws://0.0.0.0:{args.ws_port}")
    print(f"{'='*70}\n")

    # Create analyzer
    analyzer = PacketAnalyzer(
        iface=args.iface,
        home_ssid=args.ssid,
        expected_bssids=args.expected_bssid,
        expected_bssid_count=args.expected_count,
        deauth_threshold=args.deauth_threshold,
        deauth_window=args.deauth_window,
        rogue_bssid_tolerance=args.rogue_tolerance,
        beacon_retention=args.beacon_retention,
    )

    # Create frontend bridge
    bridge = FrontendBridge(analyzer)

    # Start analyzer in a background thread
    analyzer_thread = threading.Thread(
        target=analyzer.start, args=(channels, args.hop_interval), daemon=True
    )
    analyzer_thread.start()

    # Run frontend servers
    def signal_handler(sig, frame):
        print("\n\nShutting down...")
        bridge.stop_analyzer()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        asyncio.run(run_services(bridge, http_port=args.http_port, ws_port=args.ws_port))
    except KeyboardInterrupt:
        pass
    finally:
        bridge.stop_analyzer()
        print("Analyzer stopped.")


if __name__ == "__main__":
    main()
