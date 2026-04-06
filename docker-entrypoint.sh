#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         Helogale WiFi Intrusion Detection System            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Parse environment variables with defaults
IFACE="${HELOGALE_IFACE:-wlan0}"
SSID="${HELOGALE_SSID:-}"
EXPECTED_BSSIDS="${HELOGALE_EXPECTED_BSSIDS:-}"
HTTP_PORT="${HELOGALE_HTTP_PORT:-8080}"
WS_PORT="${HELOGALE_WS_PORT:-8765}"
CHANNELS="${HELOGALE_CHANNELS:-1,6,11,13}"
HOP_INTERVAL="${HELOGALE_HOP_INTERVAL:-5.0}"
DEAUTH_THRESHOLD="${HELOGALE_DEAUTH_THRESHOLD:-5}"
DEAUTH_WINDOW="${HELOGALE_DEAUTH_WINDOW:-10}"

# Validate required parameters
if [ -z "$SSID" ]; then
    echo -e "${RED}✗ Error: HELOGALE_SSID environment variable not set${NC}"
    echo "  Set it with: -e HELOGALE_SSID='YourNetworkName'"
    exit 1
fi

# Display configuration
echo -e "${GREEN}Configuration:${NC}"
echo "  Interface:        $IFACE"
echo "  Network (SSID):   $SSID"
if [ -n "$EXPECTED_BSSIDS" ]; then
    echo "  BSSIDs:           $EXPECTED_BSSIDS"
fi
echo "  HTTP Port:        $HTTP_PORT"
echo "  WebSocket Port:   $WS_PORT"
echo "  Channels:         $CHANNELS"
echo "  Hop Interval:     ${HOP_INTERVAL}s"
echo "  Deauth Alert:     $DEAUTH_THRESHOLD frames in ${DEAUTH_WINDOW}s"
echo ""

# Check if wireless interface exists
echo -e "${YELLOW}→ Checking wireless interface...${NC}"
if ! ip link show "$IFACE" > /dev/null 2>&1; then
    echo -e "${RED}✗ Error: Interface $IFACE not found${NC}"
    echo "  Available interfaces:"
    ip link show type wlan | grep '^[0-9]' || echo "  (none found)"
    exit 1
fi
echo -e "${GREEN}✓ Interface $IFACE found${NC}"

# Check if interface is up
if ! ip link show "$IFACE" | grep -q "UP"; then
    echo -e "${YELLOW}→ Bringing interface up...${NC}"
    ip link set "$IFACE" up
fi

# Try to enable monitor mode
echo -e "${YELLOW}→ Checking monitor mode support...${NC}"
CURRENT_MODE=$(iw dev "$IFACE" link 2>/dev/null | grep "Mode:" | awk '{print $2}' || echo "unknown")
echo "  Current mode: $CURRENT_MODE"

if [ "$CURRENT_MODE" != "Monitor" ]; then
    echo -e "${YELLOW}→ Attempting to enable monitor mode...${NC}"
    
    # Try to set to monitor mode
    if ip link set "$IFACE" down 2>/dev/null; then
        if iw dev "$IFACE" set type monitor 2>/dev/null; then
            if ip link set "$IFACE" up 2>/dev/null; then
                echo -e "${GREEN}✓ Monitor mode enabled${NC}"
            else
                echo -e "${RED}✗ Failed to bring interface up${NC}"
                exit 1
            fi
        else
            echo -e "${RED}✗ Failed to set monitor mode${NC}"
            echo "  Some adapters don't support monitor mode"
            echo "  Check your wireless adapter capabilities"
            exit 1
        fi
    else
        echo -e "${RED}✗ Failed to bring interface down${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓ Already in monitor mode${NC}"
fi

# Build the command
echo ""
echo -e "${YELLOW}→ Starting Helogale analyzer...${NC}"
echo ""

CMD="python -m helogale.examples.run_with_frontend"
CMD="$CMD --iface '$IFACE'"
CMD="$CMD --ssid '$SSID'"
CMD="$CMD --channels '$CHANNELS'"
CMD="$CMD --hop-interval '$HOP_INTERVAL'"
CMD="$CMD --deauth-threshold '$DEAUTH_THRESHOLD'"
CMD="$CMD --deauth-window '$DEAUTH_WINDOW'"
CMD="$CMD --http-port '$HTTP_PORT'"
CMD="$CMD --ws-port '$WS_PORT'"

if [ -n "$EXPECTED_BSSIDS" ]; then
    # Parse comma-separated BSSIDs
    IFS=',' read -ra BSSIDS <<< "$EXPECTED_BSSIDS"
    for bssid in "${BSSIDS[@]}"; do
        bssid=$(echo "$bssid" | xargs)  # Trim whitespace
        if [ -n "$bssid" ]; then
            CMD="$CMD --expected-bssid '$bssid'"
        fi
    done
fi

echo -e "${GREEN}✓ Configuration complete${NC}"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Helogale is now running!${NC}"
echo ""
echo -e "${BLUE}Access the dashboard:${NC}"
echo "  HTTP API:    http://$(hostname -I | awk '{print $1}'):$HTTP_PORT/api"
echo "  WebSocket:   ws://$(hostname -I | awk '{print $1}'):$WS_PORT"
echo "  Dashboard:   Open dashboard.html and configure API to:"
echo "               http://localhost:$HTTP_PORT"
echo ""
echo -e "${BLUE}Monitoring:${NC}"
echo "  SSID:        $SSID"
echo "  Interface:   $IFACE"
echo "  Channels:    $CHANNELS"
echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
echo ""

# Execute the command
eval "$CMD"
