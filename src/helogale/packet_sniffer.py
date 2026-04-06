import argparse
import os
import sys
import time
from helogale import wifi_hardware_utils
from scapy.all import (
    AsyncSniffer,
    Dot11Deauth,
    Dot11Beacon,
    Dot11Elt,
    Dot11ProbeReq,
)
import datetime

def ensure_root():
    if os.geteuid() == 0:
        return

    print("Root privileges are required to sniff raw packets.")
    python = sys.executable
    args = ["sudo", "-E", python, *sys.argv]
    os.execvp("sudo", args)

def handle_packet(pkt):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # --- Deauthentication Detection ---
    if pkt.haslayer(Dot11Deauth):
        src = pkt.addr2
        dst = pkt.addr1
        print(f"[{ts}] ⚠️ Deauth detected: {src} → {dst}")
        return

    # --- Beacon Frame Detection (Evil Twin Monitoring) ---
    if pkt.haslayer(Dot11Beacon):
        ssid = pkt[Dot11Elt].info.decode(errors="ignore")
        bssid = pkt.addr2
        channel = None

        # Extract channel from tagged parameters
        elt = pkt.getlayer(Dot11Elt)
        while elt:
            if elt.ID == 3:  # DS Parameter Set (channel)
                channel = elt.info[0]
                break
            elt = elt.payload.getlayer(Dot11Elt)

        print(f"[{ts}] 📡 Beacon: SSID='{ssid}' BSSID={bssid} CH={channel}")
        return

    # --- Probe Requests (optional, useful for tracking devices) ---
    if pkt.haslayer(Dot11ProbeReq):
        src = pkt.addr2
        ssid = pkt[Dot11Elt].info.decode(errors="ignore")
        print(f"[{ts}] 🔍 Probe Request: {src} looking for '{ssid}'")
        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Packet sniffer for monitor-mode WiFi interfaces")
    parser.add_argument("--iface", default="wlan0", help="Monitor-mode interface to use")
    parser.add_argument("--channel", type=int, help="Channel to lock the monitor interface to")
    parser.add_argument("--channels", help="Comma-separated channels to hop through, e.g. 1,6,11")
    parser.add_argument("--hop-interval", type=float, default=5.0, help="Seconds to wait on each channel while hopping")
    args = parser.parse_args()

    ensure_root()

    iface = args.iface
    current_mode = wifi_hardware_utils.get_interface_mode(iface)
    current_channel = wifi_hardware_utils.get_interface_channel(iface)
    print(f"Interface {iface}: mode={current_mode} channel={current_channel}")

    if current_mode != "monitor":
        print(f"Interface {iface} is not in monitor mode.")
        if wifi_hardware_utils.enable_monitor_mode(iface, verbose=True):
            print(f"Switched {iface} into monitor mode.")
            current_mode = "monitor"
        else:
            print(f"Failed to switch {iface} into monitor mode.")
            sys.exit(1)

    if args.channel is not None:
        channels = [args.channel]
    elif args.channels is not None:
        channels = [int(c.strip()) for c in args.channels.split(",") if c.strip()]
    else:
        channels = list(range(1, 14))

    if args.channel is None and args.channels is None:
        print(f"Auto-hopping channels: {channels}")
    else:
        print(f"Using channel sequence: {channels}")

    if channels:
        if wifi_hardware_utils.set_interface_channel(iface, channels[0], verbose=True):
            print(f"Starting on channel {channels[0]}")
            current_channel = channels[0]
        else:
            print(f"Failed to set {iface} to initial channel {channels[0]}")
            sys.exit(1)

    print(f"Sniffing on {iface} (mode={current_mode}, channel={current_channel})…")
    sniffer = AsyncSniffer(iface=iface, prn=handle_packet, store=False)
    sniffer.start()

    try:
        if len(channels) == 1:
            while True:
                time.sleep(1)
        else:
            while True:
                for channel in channels:
                    if wifi_hardware_utils.set_interface_channel(iface, channel, verbose=False):
                        print(f"Hopped {iface} to channel {channel}")
                    else:
                        print(f"Failed to hop {iface} to channel {channel}")
                    time.sleep(args.hop_interval)
    except KeyboardInterrupt:
        print("Stopping sniffing...")
        sniffer.stop()
        sniffer.join()
