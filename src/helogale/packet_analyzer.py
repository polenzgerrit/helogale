import argparse
import datetime
import os
import sys
import threading
import time
from collections import defaultdict, deque
from typing import Callable, Iterable

from helogale import wifi_hardware_utils
from scapy.all import AsyncSniffer, Dot11Beacon, Dot11Deauth, Dot11Elt, Dot11ProbeReq


def ensure_root():
    if os.geteuid() == 0:
        return

    print("Root privileges are required to sniff raw packets.")
    python = sys.executable
    args = ["sudo", "-E", python, *sys.argv]
    os.execvp("sudo", args)


class PacketAnalyzer:
    def __init__(
        self,
        iface: str,
        home_ssid: str,
        expected_bssids: Iterable[str] | None = None,
        expected_bssid_count: int | None = None,
        deauth_threshold: int = 5,
        deauth_window: int = 10,
        rogue_bssid_tolerance: int = 0,
        beacon_retention: int = 60,
        event_callback: Callable[[dict], None] | None = None,
    ):
        self.iface = iface
        self.home_ssid = home_ssid
        self.expected_bssids = set(x.lower() for x in (expected_bssids or []))
        self.expected_bssid_count = expected_bssid_count if expected_bssid_count is not None else len(self.expected_bssids)
        self.deauth_threshold = deauth_threshold
        self.deauth_window = deauth_window
        self.rogue_bssid_tolerance = rogue_bssid_tolerance
        self.beacon_retention = beacon_retention
        self.event_callback = event_callback
        self.state_lock = threading.Lock()

        self.deauth_events: deque[float] = deque()
        self.beacon_events: defaultdict[str, deque[float]] = defaultdict(deque)
        self.seen_bssids: set[str] = set()
        self.last_alerted_extra_bssid_count: int | None = None
        self.events: list[dict] = []
        self.alerts: list[dict] = []
        self._listeners: list[Callable[[dict], None]] = []
        self.current_channel: int | None = None
        self._next_event_id = 1
        self._stop_event = threading.Event()
        self._sniffer = None

    def _emit_event(self, event: dict) -> None:
        if self.event_callback:
            try:
                self.event_callback(event)
            except Exception:
                pass

        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                pass

    def add_event_listener(self, listener: Callable[[dict], None]) -> None:
        with self.state_lock:
            if listener not in self._listeners:
                self._listeners.append(listener)

    def remove_event_listener(self, listener: Callable[[dict], None]) -> None:
        with self.state_lock:
            if listener in self._listeners:
                self._listeners.remove(listener)

    @property
    def is_running(self) -> bool:
        return self._sniffer is not None and not self._stop_event.is_set()

    def get_recent_events(self, limit: int = 100) -> list[dict]:
        with self.state_lock:
            return list(self.events[-limit:])

    def get_recent_alerts(self, limit: int = 50) -> list[dict]:
        with self.state_lock:
            return list(self.alerts[-limit:])

    def get_state_snapshot(self) -> dict:
        with self.state_lock:
            return {
                "iface": self.iface,
                "home_ssid": self.home_ssid,
                "expected_bssids": list(self.expected_bssids),
                "expected_bssid_count": self.expected_bssid_count,
                "observed_bssid_count": self._home_bssid_count(),
                "seen_bssids": sorted(self.seen_bssids),
                "current_channel": self.current_channel,
                "is_running": self.is_running,
                "event_count": len(self.events),
                "alert_count": len(self.alerts),
                "last_alerted_extra_bssid_count": self.last_alerted_extra_bssid_count,
            }

    def stop(self) -> None:
        self._stop_event.set()
        if self._sniffer is not None:
            self._sniffer.stop()
            self._sniffer.join()
            self._sniffer = None

    def _log(self, message: str, kind: str = "log", data: dict | None = None) -> None:
        prefix = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        event = {
            "id": self._next_event_id,
            "ts": prefix,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "kind": kind,
            "severity": "warning" if kind == "alert" else "info",
            "message": message,
            "source": "packet_analyzer",
            "data": data or {},
        }
        text = f"[{prefix}] {message}"
        print(text)
        with self.state_lock:
            self.events.append(event)
            if kind == "alert":
                self.alerts.append(event)
            self._next_event_id += 1
        self._emit_event(event)

    def _prune_old_beacons(self) -> None:
        now = time.time()
        for bssid, timestamps in list(self.beacon_events.items()):
            while timestamps and now - timestamps[0] > self.beacon_retention:
                timestamps.popleft()
            if not timestamps:
                del self.beacon_events[bssid]

    def _home_bssid_count(self) -> int:
        self._prune_old_beacons()
        return len(self.beacon_events)

    def _detect_deauth_spike(self) -> None:
        now = time.time()
        self.deauth_events.append(now)

        while self.deauth_events and now - self.deauth_events[0] > self.deauth_window:
            self.deauth_events.popleft()

        if len(self.deauth_events) >= self.deauth_threshold:
            self._log(
                f"⚠️ Deauth spike: {len(self.deauth_events)} deauth frames in {self.deauth_window}s",
                kind="alert",
                data={
                    "deauth_count": len(self.deauth_events),
                    "window": self.deauth_window,
                },
            )

    def _detect_rogue_aps(self, bssid: str) -> None:
        observed_count = self._home_bssid_count()
        extra = observed_count - self.expected_bssid_count

        if extra > self.rogue_bssid_tolerance:
            if self.last_alerted_extra_bssid_count != observed_count:
                self.last_alerted_extra_bssid_count = observed_count
                data = {
                    "observed_count": observed_count,
                    "expected_count": self.expected_bssid_count,
                    "extra": extra,
                    "bssid": bssid,
                }
                self._log(
                    f"⚠️ Unexpected AP count for SSID '{self.home_ssid}': {observed_count} unique BSSIDs seen",
                    kind="alert",
                    data=data,
                )
                self._log(
                    f"    Expected {self.expected_bssid_count} BSSIDs, saw {extra} more than expected",
                    kind="alert",
                    data=data,
                )
                if bssid.lower() not in self.expected_bssids:
                    self._log(f"    New rogue BSSID: {bssid}", kind="alert", data=data)
                else:
                    self._log(f"    Additional BSSID activity detected: {bssid}", kind="alert", data=data)

    def _detect_ssid_mac_increase(self) -> None:
        count = self._home_bssid_count()
        if count > self.expected_bssid_count + self.rogue_bssid_tolerance:
            self._log(
                f"⚠️ Unexpected SSID broadcast increase: {count} unique BSSIDs broadcasting '{self.home_ssid}'",
                kind="alert",
                data={
                    "observed_count": count,
                    "expected_count": self.expected_bssid_count,
                },
            )

    def _extract_ssid(self, pkt) -> str | None:
        ssid_elt = pkt.getlayer(Dot11Elt)
        while ssid_elt is not None:
            if ssid_elt.ID == 0:
                try:
                    return ssid_elt.info.decode(errors="ignore")
                except Exception:
                    return None
            ssid_elt = ssid_elt.payload.getlayer(Dot11Elt)
        return None

    def _extract_channel(self, pkt) -> int | None:
        elt = pkt.getlayer(Dot11Elt)
        while elt is not None:
            if elt.ID == 3 and elt.info:
                return elt.info[0]
            elt = elt.payload.getlayer(Dot11Elt)
        return None

    def _handle_beacon(self, pkt) -> None:
        ssid = self._extract_ssid(pkt)
        if ssid != self.home_ssid:
            return

        bssid = pkt.addr2
        if not bssid:
            return

        channel = self._extract_channel(pkt)
        self._prune_old_beacons()
        self.beacon_events[bssid.lower()].append(time.time())
        self.seen_bssids.add(bssid.lower())

        is_expected = bssid.lower() in self.expected_bssids
        if not self.expected_bssids or not is_expected:
            self._log(
                f"📡 Beacon: SSID='{ssid}' BSSID={bssid} CH={channel}",
                kind="event",
                data={"ssid": ssid, "bssid": bssid, "channel": channel},
            )
            if not is_expected:
                self._log(
                    f"    New BSSID for {ssid}: {bssid}",
                    kind="alert",
                    data={"ssid": ssid, "bssid": bssid, "channel": channel},
                )

        self._detect_ssid_mac_increase()
        self._detect_rogue_aps(bssid)

    def _handle_probe(self, pkt) -> None:
        ssid = self._extract_ssid(pkt)
        if ssid is None:
            return

        src = pkt.addr2
        self._log(
            f"🔍 Probe request from {src} for '{ssid}'",
            kind="event",
            data={"ssid": ssid, "src": src},
        )

    def _handle_deauth(self, pkt) -> None:
        src = pkt.addr2
        dst = pkt.addr1
        self._log(
            f"⚠️ Deauth frame: {src} → {dst}",
            kind="event",
            data={"src": src, "dst": dst},
        )
        self._detect_deauth_spike()

    def _categorize_packet(self, pkt) -> None:
        if pkt.haslayer(Dot11Deauth):
            self._handle_deauth(pkt)
            return

        if pkt.haslayer(Dot11Beacon):
            self._handle_beacon(pkt)
            return

        if pkt.haslayer(Dot11ProbeReq):
            self._handle_probe(pkt)
            return

    def start(self, channels: list[int] | None = None, hop_interval: float = 5.0) -> None:
        self._log(
            f"Starting packet analyzer on {self.iface} for SSID '{self.home_ssid}'"
        )

        channels = channels or list(range(1, 14))
        self._stop_event.clear()
        self._sniffer = AsyncSniffer(iface=self.iface, prn=self._categorize_packet, store=False)
        self._sniffer.start()

        try:
            if len(channels) == 1:
                self.current_channel = channels[0]
                self._log(f"Capturing on channel {channels[0]}", kind="event", data={"channel": channels[0]})
                while not self._stop_event.wait(1):
                    pass
            else:
                self._log(f"Channel hopping: {channels} (interval={hop_interval}s)")
                while not self._stop_event.is_set():
                    for channel in channels:
                        if self._stop_event.is_set():
                            break
                        if wifi_hardware_utils.set_interface_channel(self.iface, channel, verbose=False):
                            self.current_channel = channel
                            self._log(
                                f"Hopped {self.iface} to channel {channel}",
                                kind="event",
                                data={"channel": channel},
                            )
                        else:
                            self._log(
                                f"Failed to set {self.iface} to channel {channel}",
                                kind="alert",
                                data={"channel": channel},
                            )
                        self._stop_event.wait(hop_interval)
        finally:
            self._log("Stopping packet analyzer...", kind="event")
            self.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wi-Fi packet analyzer for SSID/rogue AP/deauth detection")
    parser.add_argument("--iface", default="wlx9cefd5f67596", help="Monitor-mode interface to use")
    parser.add_argument("--ssid", required=True, help="Home SSID to monitor")
    parser.add_argument("--expected-bssid", action="append", default=[], help="Expected AP BSSID for the home network")
    parser.add_argument("--expected-count", type=int, help="Expected number of APs broadcasting the home SSID")
    parser.add_argument("--deauth-threshold", type=int, default=5, help="Number of deauths in the deauth-window that triggers an alert")
    parser.add_argument("--deauth-window", type=int, default=10, help="Window in seconds for deauth spike detection")
    parser.add_argument("--rogue-tolerance", type=int, default=0, help="Allowed extra BSSIDs beyond the expected count before alerting")
    parser.add_argument("--beacon-retention", type=int, default=60, help="Seconds of beacon history to retain for SSID tracking")
    parser.add_argument("--channels", help="Comma-separated channels to hop through, default all channels")
    parser.add_argument("--hop-interval", type=float, default=5.0, help="Seconds to stay on each channel while hopping")
    args = parser.parse_args()

    ensure_root()
    if args.channels is not None:
        channels = [int(c.strip()) for c in args.channels.split(",") if c.strip()]
    else:
        channels = list(range(1, 14))

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
    analyzer.start(channels=channels, hop_interval=args.hop_interval)
