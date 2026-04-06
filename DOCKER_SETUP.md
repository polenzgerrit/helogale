# Docker Deployment Guide

This guide explains how to run Helogale as a Docker container for network-accessible WiFi intrusion detection.

## Prerequisites

### Host Requirements

- Docker installed and running
- Docker Compose (optional, but recommended)
- A wireless adapter that supports monitor mode (most modern adapters do)
- Linux host (WiFi monitoring requires Linux kernel)
- Host network access to the wireless interface

### Wireless Adapter Support

Most WiFi adapters support monitor mode. To check yours:

```bash
# List wireless interfaces
ip link show type wlan

# Check capabilities
iw phy
```

If your adapter doesn't support monitor mode, you may need:
- **Raspberry Pi**: Use `iw` to check; most adapters work
- **Virtual Machine**: Pass through physical adapter or use bridged network
- **Cloud VM**: Monitor mode may not be available

## Quick Start (Docker Compose)

### 1. Basic Setup

The simplest way to get started:

```bash
cd /path/to/helogale

# Create a .env file with your configuration
cat > .env << 'EOF'
HELOGALE_IFACE=wlan0
HELOGALE_SSID=MyNetwork
HELOGALE_HTTP_PORT=8080
HELOGALE_WS_PORT=8765
EOF

# Start the container
docker-compose up -d
```

### 2. Verify It's Running

```bash
# Check container logs
docker-compose logs -f helogale

# Check API is responding
curl http://localhost:8080/api/state | jq

# Check for alerts
curl http://localhost:8080/api/alerts | jq
```

### 3. Access the Dashboard

**Option A: Direct HTML (recommended for local network)**

1. Copy `dashboard.html` to your local machine
2. Open it in a browser
3. When prompted for API URL, enter: `http://<host-ip>:8080`
   - Replace `<host-ip>` with the IP of your Docker host
4. The dashboard will auto-connect and start polling

**Option B: Serve via HTTP**

```bash
# On the Docker host
cd /path/to/helogale
python -m http.server 8888

# In browser: http://localhost:8888/dashboard.html
```

### 4. Configure Monitoring Parameters

Edit `.env` before starting or update `docker-compose.yml`:

```bash
# Example: Monitor specific channels
HELOGALE_CHANNELS=1,6,11

# Example: Add expected BSSIDs
HELOGALE_EXPECTED_BSSIDS=aa:bb:cc:dd:ee:ff,11:22:33:44:55:66

# Example: Adjust deauth detection
HELOGALE_DEAUTH_THRESHOLD=5
HELOGALE_DEAUTH_WINDOW=10
```

All options:

| Variable | Default | Description |
|----------|---------|-------------|
| `HELOGALE_IFACE` | `wlan0` | Wireless interface |
| `HELOGALE_SSID` | (required) | Network name to monitor |
| `HELOGALE_EXPECTED_BSSIDS` | (empty) | Comma-separated MAC addresses |
| `HELOGALE_HTTP_PORT` | `8080` | HTTP API port |
| `HELOGALE_WS_PORT` | `8765` | WebSocket port |
| `HELOGALE_CHANNELS` | `1,6,11,13` | Channels to scan |
| `HELOGALE_HOP_INTERVAL` | `5.0` | Seconds per channel |
| `HELOGALE_DEAUTH_THRESHOLD` | `5` | Deauth frames before alert |
| `HELOGALE_DEAUTH_WINDOW` | `10` | Deauth detection window (seconds) |

## Quick Start (Docker CLI)

If you prefer not to use Docker Compose:

```bash
# Build the image
docker build -t helogale:latest .

# Run the container
docker run -d \
  --name helogale \
  --net host \
  --privileged \
  -e HELOGALE_SSID="MyNetwork" \
  -e HELOGALE_IFACE="wlan0" \
  -e HELOGALE_HTTP_PORT="8080" \
  -e HELOGALE_WS_PORT="8765" \
  helogale:latest

# View logs
docker logs -f helogale

# Stop the container
docker stop helogale
docker rm helogale
```

## Advanced Configuration

### Docker Compose Override

Create `docker-compose.override.yml` for local customizations:

```yaml
version: '3.8'

services:
  helogale:
    environment:
      - HELOGALE_IFACE=wlp3s0
      - HELOGALE_HTTP_PORT=9000
      - HELOGALE_DEAUTH_THRESHOLD=10
    ports:
      - "9000:8080"
      - "9765:8765"
```

Then just use: `docker-compose up`

### Multiple Instances

Monitor multiple networks or interfaces:

```yaml
version: '3.8'

services:
  helogale-home:
    build: .
    environment:
      - HELOGALE_IFACE=wlan0
      - HELOGALE_SSID=HomeNetwork
      - HELOGALE_HTTP_PORT=8080
  
  helogale-guest:
    build: .
    environment:
      - HELOGALE_IFACE=wlan1
      - HELOGALE_SSID=GuestNetwork
      - HELOGALE_HTTP_PORT=8081
```

### Network Modes

**Option 1: host (Recommended for WiFi)**
```yaml
network_mode: host
```
- Direct access to wireless interface
- No port mapping needed
- Best performance

**Option 2: bridge (If host is unavailable)**
```yaml
ports:
  - "8080:8080"
  - "8765:8765"
```
- Less direct hardware access
- Requires port mapping
- May not support monitor mode

### Persistent Logging

Store logs on the host:

```yaml
services:
  helogale:
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
```

Then view: `tail -f logs/helogale.log`

### Resource Limits

Control container resource usage:

```yaml
services:
  helogale:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 256M
        reservations:
          cpus: '0.5'
          memory: 128M
```

## Networking

### Accessing from Another Machine

From another machine on the same network:

```bash
# Get the host IP
ip addr show

# Access API from another machine
curl http://<host-ip>:8080/api/state | jq

# Connect dashboard to
# Enter in dashboard.html: http://<host-ip>:8080
```

### Port Forwarding

If the container host is behind a firewall:

```bash
# SSH tunnel
ssh -L 8080:localhost:8080 user@host

# Then access locally
curl http://localhost:8080/api/state
```

## Troubleshooting

### Container won't start: "Interface not found"

```bash
# Check interfaces on host
ip link show type wlan

# Ensure interface is available
# Some adapters are disconnected by power management
sudo rfkill unblock all
ip link set wlan0 up
```

### Monitor mode not being set

```bash
# Check adapter capabilities
iw phy

# Try manually on host
sudo ip link set wlan0 down
sudo iw dev wlan0 set type monitor
sudo ip link set wlan0 up

# Check mode
iw dev wlan0 link
```

### Permission denied errors

```bash
# Ensure container runs as root
# In docker-compose.yml:
services:
  helogale:
    user: "0:0"  # root:root

# Or use --privileged flag
docker run --privileged ...
```

### No events captured

```bash
# Verify monitor mode is active
docker exec helogale iw dev wlan0 link

# Check interface is receiving packets
docker exec helogale tcpdump -i wlan0 -c 10

# Verify SSID matches exactly (case-sensitive)
# Check channel hopping
docker logs helogale | grep "Hopped\|channel"
```

### API not responding

```bash
# Check if ports are accessible
curl http://localhost:8080/api/state

# Verify port mapping
docker port helogale

# Check container is running
docker ps | grep helogale

# View logs
docker logs helogale
```

### WebSocket connection fails

```bash
# Verify WebSocket port is accessible
telnet localhost 8765

# Or with curl
curl -i -N -H "Connection: Upgrade" -H "Upgrade: websocket" \
  http://localhost:8765
```

## Performance Tuning

### For Raspberry Pi

```yaml
deploy:
  resources:
    limits:
      cpus: '1.0'
      memory: 128M
    reservations:
      cpus: '0.5'
      memory: 64M

environment:
  - HELOGALE_HOP_INTERVAL=10.0  # Stay longer per channel
  - HELOGALE_CHANNELS=1,6,11    # Fewer channels
```

### For High-Traffic Networks

```yaml
environment:
  - HELOGALE_CHANNELS=1,2,3,4,5,6,7,8,9,10,11,12,13  # All channels
  - HELOGALE_HOP_INTERVAL=2.0   # Shorter dwell time
  - HELOGALE_BEACON_RETENTION=120  # Keep longer history
```

### Memory Optimization

```python
# Edit startup command in docker-entrypoint.sh
# Reduce beacon retention
--beacon-retention 30
```

## Stopping & Cleanup

```bash
# Stop container
docker-compose down

# Remove container and volumes
docker-compose down -v

# Remove image
docker image rm helogale:latest

# Clean up all Docker resources
docker system prune -a
```

## Production Deployment

### Using a Reverse Proxy

For external access, use nginx or Apache:

```nginx
server {
    listen 80;
    server_name helogale.example.com;

    location /api/ {
        proxy_pass http://localhost:8080;
        proxy_buffering off;
    }

    location /ws {
        proxy_pass http://localhost:8765;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location / {
        root /var/www/helogale;
        try_files $uri /dashboard.html;
    }
}
```

### SSL/TLS Support

```bash
# Generate self-signed cert
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365

# Use with reverse proxy (nginx)
listen 443 ssl;
ssl_certificate /etc/nginx/cert.pem;
ssl_certificate_key /etc/nginx/key.pem;
```

### Authentication Layer

Add API authentication (consider Nginx auth_basic or implement in FastAPI):

```nginx
location /api/ {
    auth_basic "Helogale API";
    auth_basic_user_file /etc/nginx/.htpasswd;
    
    proxy_pass http://localhost:8080;
}
```

### Kubernetes Deployment

A basic Kubernetes manifest:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: helogale
spec:
  hostNetwork: true
  containers:
  - name: helogale
    image: helogale:latest
    securityContext:
      privileged: true
    env:
    - name: HELOGALE_SSID
      value: "MyNetwork"
    - name: HELOGALE_IFACE
      value: "wlan0"
    ports:
    - containerPort: 8080
    - containerPort: 8765
```

## Development

### Building the Image

```bash
# Build with specific tag
docker build -t helogale:dev .

# Build with build args
docker build \
  --build-arg PYTHON_VERSION=3.14 \
  -t helogale:custom .
```

### Interactive Shell

```bash
# Debug container
docker run -it --rm \
  --net host \
  --privileged \
  -e HELOGALE_SSID=Debug \
  helogale:latest /bin/bash
```

### View Container Logs

```bash
# Stream logs
docker logs -f helogale

# Get last 100 lines
docker logs --tail 100 helogale

# With timestamps
docker logs -t helogale
```

### Execute Commands in Running Container

```bash
# Check interface status
docker exec helogale ip link show

# View current events
docker exec helogale curl http://localhost:8080/api/events | jq

# Run a one-off command
docker exec helogale iw dev wlan0 link
```

## Common Use Cases

### Use Case 1: Home Network Monitoring

```bash
docker-compose up -d -e \
  HELOGALE_SSID="HomeWiFi" \
  HELOGALE_EXPECTED_BSSIDS="aa:bb:cc:dd:ee:ff"

# Access dashboard on local network
# http://<raspberry-pi-ip>:8080/dashboard.html
```

### Use Case 2: Network Security Testing

```bash
docker run --rm \
  --net host \
  --privileged \
  -e HELOGALE_SSID="TestNetwork" \
  -e HELOGALE_DEAUTH_THRESHOLD=3 \
  -e HELOGALE_CHANNELS="6" \
  helogale:latest
```

### Use Case 3: 24/7 Monitoring with Alerting

```yaml
# docker-compose.yml with persistence
services:
  helogale:
    # ... config ...
    restart: always
    volumes:
      - helogale_data:/app/data
      - ./logs:/app/logs
    
    # Forward alerts to external system
    environment:
      - HELOGALE_WEBHOOK_URL=https://example.com/alerts
```

### Use Case 4: Multiple Network Monitoring

```bash
# Run two instances, one per SSID
docker-compose up -d

# (with multiple service definitions in compose file)
```

## FAQ

**Q: Does the container need to run on my router?**
A: No, any Linux machine with WiFi can run it. Better on a dedicated unit like Raspberry Pi.

**Q: Can I run this on a virtual machine?**
A: Yes, if you pass through the physical wireless adapter. NAT or bridged networking with virtual adapters won't work for monitor mode.

**Q: What's the minimum hardware?**
A: Raspberry Pi 4 or better. Older Pi models may struggle with channel hopping.

**Q: Can I monitor multiple networks?**
A: Yes, run multiple containers with different interfaces/SSIDs.

**Q: How much network bandwidth does it use?**
A: Very little—only passive monitoring. Minimal traffic sent.

**Q: Can I access the dashboard from outside my network?**
A: Yes, with a reverse proxy (nginx) and proper security (authentication, HTTPS).

**Q: How do I update the container?**
A: Rebuild the image and restart: `docker-compose down && docker build . && docker-compose up -d`

## Support & Documentation

- [Main README](README.md) — Features and overview
- [Frontend Guide](FRONTEND_GUIDE.md) — API documentation
- [Quick Reference](QUICK_REFERENCE.md) — API cheat sheet
- [GitHub Issues](https://github.com/yourrepo/helogale/issues)

## License

See [LICENSE](../LICENSE) file.

---

**Last Updated**: 2026-04-05  
**Docker Version**: 20.10+  
**Docker Compose Version**: 1.29+
