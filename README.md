# helogale

A lightweight, container-friendly home WiFi intrusion detection and alerting system built with Python and open-source tools. Monitors your home network for deauthentication attacks, rogue access points, and SSID spoofing.

<img width="125" height="111" alt="image" src="https://github.com/user-attachments/assets/ce86430f-6dd0-418f-b6cf-fe4697196b55" />

## Features

- ✅ **Passive Monitor-Mode Sniffing**: Captures IEEE 802.11 frames without connecting to the network
- ✅ **Threat Detection**: Identifies deauth attacks, rogue APs, SSID spoofing, and PKT floods
- ✅ **Channel Hopping**: Scans all WiFi channels for comprehensive coverage
- ✅ **Structured Event API**: Real-time events and alerts for frontend integration
- ✅ **HTML Dashboard**: Responsive web UI with live event monitoring and alerts
- ✅ **REST + WebSocket APIs**: HTTP endpoints and WebSocket push for client integration
- ✅ **Thread-Safe**: Concurrent event handling with proper locking
- ✅ **Low Resource**: Minimal overhead on Raspberry Pi / embedded systems

## Quick Start

### Prerequisites

```bash
# Linux only (requires iw, ip, and sudo)
sudo apt-get install wireless-tools iw
python3.14 -m pip install poetry
cd helogale
poetry install
```

### Run the Analyzer + Dashboard

```bash
# Terminal 1: Start the analyzer with HTTP/WebSocket servers
sudo poetry run python -m helogale.examples.run_with_frontend \
    --iface wlan0 \
    --ssid "MyNetwork" \
    --expected-bssid "aa:bb:cc:dd:ee:ff"

# Terminal 2: Open dashboard in a browser
# Navigate to: file:///path/to/helogale/dashboard.html
# Or: open dashboard.html with a local HTTP server
```

Then open [dashboard.html](dashboard.html) in your browser—it will auto-connect to the API at `http://localhost:8080`.

### Docker (Recommended for Network Deployment)

Want to run Helogale on a Raspberry Pi or other machine and access from your network? Use Docker:

```bash
# Clone the repository and build the container
docker-compose up -d \
  -e HELOGALE_SSID="MyNetwork" \
  -e HELOGALE_IFACE="wlan0"

# Access the API and dashboard from any machine on your network
# HTTP API: http://<host-ip>:8080/api
# Dashboard: Open dashboard.html and point to http://<host-ip>:8080
```

**Features:**
- 🐳 Single command to deploy
- 🔌 Network-accessible from any device
- 📊 Built-in HTTP API and WebSocket server
- ⚙️ Easy configuration via environment variables
- 🎯 Perfect for Raspberry Pi or NAS

See [DOCKER_SETUP.md](DOCKER_SETUP.md) for complete Docker documentation.

## Architecture

```
┌─────────────────────────────────────────────┐
│         Packet Analyzer (Core)              │
│  • Monitor-mode sniffing                    │
│  • Beacon/probe/deauth categorization       │
│  • Channel hopping                          │
│  • Alert generation on threats              │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│      Structured Event API                   │
│  • Thread-safe state management             │
│  • Event callbacks & listeners              │
│  • State snapshots & history queries        │
└─────────────────────────────────────────────┘
                    ↓
┌─────────┬───────────────────────┬───────────┐
│ REST    │  WebSocket Server     │ Frontend  │
│ API     │  (push events)        │  Bridge   │
│ (HTTP)  │                       │           │
└─────────┴───────────────────────┴───────────┘
                    ↓
┌─────────────────────────────────────────────┐
│      Web Dashboard (JS/HTML/CSS)            │
│  • Live state monitoring                    │
│  • Alert notifications                      │
│  • Event timeline                           │
│  • BSSID tracking                           │
└─────────────────────────────────────────────┘
```

## Core Modules

| Module | Purpose |
|--------|---------|
| `wifi_hardware_utils.py` | Linux wireless interface control (monitor mode, channels) |
| `packet_sniffer.py` | Root elevation & packet capture wrapper |
| `packet_analyzer.py` | Threat detection & event emission |
| `frontend_server.py` | HTTP/WebSocket servers + event bridge |
| `examples/run_with_frontend.py` | CLI entry point + server orchestration |

## Threat Detection

### 1. Deauthentication Attacks
- Triggers when `N` deauth frames arrive within a time window
- Default: 5 deauths in 10 seconds

### 2. Rogue Access Points
- Compares observed BSSIDs to expected list
- Alerts on unexpected MAC addresses broadcasting the home SSID
- Tracks multiple legitimate APs (mesh networks)

### 3. SSID Spoofing
- Detects unusual increases in BSSID count
- Example: If you expect 1 AP, but suddenly see 3 broadcasting the same SSID

### 4. Channel Awareness
- Monitors all WiFi channels (1-13 / 1-14 depending on locale)
- Hops channels at configurable intervals (default: 5 seconds per channel)

## API Documentation

### Event Format

Every event emitted by the analyzer follows this schema:

```json
{
  "id": 42,
  "ts": "2024-01-15 14:30:45",
  "timestamp": "2024-01-15T14:30:45Z",
  "kind": "alert|event|log",
  "severity": "warning|info",
  "message": "Human-readable description",
  "source": "packet_analyzer",
  "data": {
    "deauth_count": 5,
    "bssid": "aa:bb:cc:dd:ee:ff",
    ...
  }
}
```

### PacketAnalyzer API

```python
from helogale import PacketAnalyzer, ensure_root

ensure_root()

analyzer = PacketAnalyzer(
    iface="wlan0",
    home_ssid="MyNetwork",
    expected_bssids=["aa:bb:cc:dd:ee:ff"],
    deauth_threshold=5,          # deauths before alert
    deauth_window=10,            # seconds
    rogue_bssid_tolerance=0,     # extra BSSIDs allowed
    beacon_retention=60,         # seconds to track beacons
    event_callback=lambda e: print(e)  # optional callback
)

# Start monitoring
analyzer.start(channels=[1, 6, 11], hop_interval=5.0)

# Query state
state = analyzer.get_state_snapshot()
events = analyzer.get_recent_events(limit=100)
alerts = analyzer.get_recent_alerts(limit=50)

# Stop gracefully
analyzer.stop()
```

### HTTP REST API

| Endpoint | Method | Query Params | Response |
|----------|--------|--------------|----------|
| `/api/state` | GET | — | Current analyzer state |
| `/api/events` | GET | `limit=100` | Recent events |
| `/api/alerts` | GET | `limit=50` | Recent alerts |
| `/api/stop` | POST | — | Stop analyzer |

Example:
```bash
curl http://localhost:8080/api/state | jq
curl http://localhost:8080/api/alerts?limit=10 | jq
```

### WebSocket API

Connect to `ws://localhost:8765` and send JSON commands:

```json
{"type": "get_state"}
{"type": "get_recent_events", "limit": 100}
{"type": "get_recent_alerts", "limit": 50}
{"type": "subscribe"}
{"type": "stop"}
```

Server responds with:
```json
{"type": "state", "payload": {...}}
{"type": "events", "payload": [...]}
{"type": "event", "payload": {...}}
{"type": "stopped"}
```

## CLI Usage

### Basic Monitoring

```bash
sudo poetry run python -m helogale.packet_analyzer \
    --iface wlan0 \
    --ssid "MyNetwork" \
    --expected-bssid "aa:bb:cc:dd:ee:ff" \
    --deauth-threshold 5 \
    --deauth-window 10
```

### With Frontend Servers

```bash
sudo poetry run python -m helogale.examples.run_with_frontend \
    --iface wlan0 \
    --ssid "MyNetwork" \
    --expected-bssid "aa:bb:cc:dd:ee:ff" \
    --channels "1,6,11" \
    --hop-interval 5.0 \
    --http-port 8080 \
    --ws-port 8765
```

### Configure Interface

```bash
# List wireless interfaces
sudo poetry run python -c "from helogale import get_wireless_interfaces; print(get_wireless_interfaces())"

# Enable monitor mode
sudo poetry run python -c "from helogale import enable_monitor_mode; enable_monitor_mode('wlan0')"

# Check interface mode
sudo poetry run python -c "from helogale import get_interface_mode; print(get_interface_mode('wlan0'))"
```

## Dashboard Features

The included `dashboard.html` provides:

- 📊 **Real-Time Stats**: SSID, BSSID count, channel, status
- 🚨 **Alert Feed**: Critical events with timestamps
- 📡 **BSSID Tracker**: List of observed MAC addresses
- 📋 **Event Log**: Detailed timeline of all activity
- 🔄 **Auto-Refresh**: Configurable polling interval (1-60 seconds)
- 🔔 **Desktop Notifications**: Browser notifications for new alerts
- 📱 **Responsive**: Works on desktop, tablet, and mobile

![Dashboard Screenshot](dashboard-preview.png)

## Examples

### Example 1: Simple Event Logging

```python
from helogale import PacketAnalyzer, ensure_root

ensure_root()

def on_event(event):
    if event["kind"] == "alert":
        print(f"🚨 ALERT: {event['message']}")

analyzer = PacketAnalyzer(
    iface="wlan0",
    home_ssid="MyNetwork",
    event_callback=on_event
)

analyzer.start()
```

### Example 2: Programmatic Frontend

```python
from helogale import PacketAnalyzer, ensure_root
from helogale.frontend_server import FrontendBridge, SimpleHTTPServer
import asyncio
import threading

ensure_root()

analyzer = PacketAnalyzer(iface="wlan0", home_ssid="MyNetwork")
bridge = FrontendBridge(analyzer)

# Start analyzer in background
threading.Thread(target=analyzer.start, daemon=True).start()

# Start HTTP server
asyncio.run(SimpleHTTPServer(bridge, port=8080).start())
```

### Example 3: Custom Listener

```python
from helogale import PacketAnalyzer

analyzer = PacketAnalyzer(iface="wlan0", home_ssid="MyNetwork")

# Add multiple listeners
def listener1(event):
    print(f"[Listener1] {event['message']}")

def listener2(event):
    if event["kind"] == "alert":
        # Send to database, email, etc.
        pass

analyzer.add_event_listener(listener1)
analyzer.add_event_listener(listener2)

analyzer.start()
```

## Full Frontend Integration Guide

See [FRONTEND_GUIDE.md](FRONTEND_GUIDE.md) for:
- Detailed architecture documentation
- API reference
- Production deployment patterns
- React/Vue component examples
- WebSocket best practices
- Troubleshooting

## Configuration

### Expected Parameters

- `iface`: Monitor-mode wireless interface (e.g., `wlan0`)
- `home_ssid`: Network name to monitor (e.g., `"MyNetwork"`)
- `expected_bssids`: List of legitimate MAC addresses
- `expected_bssid_count`: If unknown, derived from `expected_bssids`
- `deauth_threshold`: Number of deauths before alert (default: 5)
- `deauth_window`: Time window in seconds (default: 10)
- `rogue_bssid_tolerance`: Extra BSSIDs allowed (default: 0)
- `beacon_retention`: Seconds to track beacon history (default: 60)
- `channels`: WiFi channels to scan (default: 1-13)
- `hop_interval`: Seconds per channel (default: 5)

## Limitations

- **Linux only**: Requires Linux with `iw` and wireless adapter support
- **Passive monitoring**: Only sees management frames, not data/control frames
- **Root required**: Raw socket access requires elevated privileges
- **Single interface**: Monitors one interface per analyzer instance
- **False positives**: May alert on legitimate guest networks or mesh APs

## Troubleshooting

### "No suitable card found"

```bash
# List your wireless interfaces
ip link show type wlan

# Enable monitor mode manually
sudo ip link set wlan0 down
sudo iw dev wlan0 set type monitor
sudo ip link set wlan0 up

# Check mode
iw dev wlan0 link
```

### "Permission denied"

```bash
# Analyzer requires root to open raw sockets
sudo poetry run python -m helogale.packet_analyzer ...

# Or the script will re-execute with sudo automatically
python -m helogale.packet_analyzer ...
```

### "Only seeing probesbeacons, not everything"

1. Check you're listening on all channels: `--channels "1,6,11,13"`
2. Increase `--hop-interval` to stay longer per channel
3. Ensure monitor mode is active: `iw dev wlan0 link`
4. Check for interference: `sudo iw dev wlan0 survey` (if supported)

## Requirements

### For Bare Metal / SSH Installation
- Python 3.14+
- Linux (Debian, Ubuntu, Raspberry Pi OS, etc.)
- `iw` and wireless drivers for your network adapter
- `scapy` (installed via Poetry)

### For Docker Installation (Recommended)
- Docker and Docker Compose
- Linux host with wireless adapter support
- No Python or Poetry required on host

## Installation

### Option 1: Docker (Recommended)

```bash
# Quick start
docker-compose up -d \
  -e HELOGALE_SSID="MyNetwork" \
  -e HELOGALE_IFACE="wlan0"

# Or with configuration file
cp .env.example .env
# Edit .env with your settings
docker-compose up -d
```

See [DOCKER_SETUP.md](DOCKER_SETUP.md) for detailed Docker instructions.

### Option 2: Poetry (Bare Metal)

```bash
# Clone and install
git clone <repo>
cd helogale
poetry install

# Or with pip (requires scapy):
pip install scapy
```

## Roadmap

- [ ] Support for multiple interfaces
- [ ] Database persistence (SQLite/PostgreSQL)
- [ ] Email/SMS alerts
- [ ] Webhook integrations (Slack, Discord)
- [ ] Mobile app (React Native / Flutter)
- [ ] Geographic mapping of APs
- [ ] Machine learning anomaly detection
- [ ] Docker containerization
- [ ] Cloud deployment (AWS / Azure)

## Notes

- Must run on Linux machine
- Requires wireless adapter that supports monitor mode
- Use strong expected BSSID lists to reduce false positives
- Test alerts in your test environment first
- Keep beacon retention reasonable to avoid memory bloat

## License

See [LICENSE](LICENSE) file.

## Security Considerations

- This tool performs passive monitoring only—it does not transmit or alter network traffic
- All captured frames are processed in memory; no persistent logging by default
- Alerts should be reviewed by network administrators; false positives are possible
- Use in accordance with local laws and wireless regulations
- Do not monitor networks you don't own or have permission to monitor

## Contributing

Contributions welcome! Please submit issues and pull requests.

