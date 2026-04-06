"""Helogale: A lightweight, container-friendly home WiFi intrusion detection and alerting system."""

__version__ = "0.1.0"

from .packet_analyzer import PacketAnalyzer, ensure_root
from .wifi_hardware_utils import (
    enable_monitor_mode,
    get_interface_channel,
    get_interface_mode,
    get_wireless_interfaces,
    interface_supports_monitor_mode,
    set_interface_channel,
)

__all__ = [
    "PacketAnalyzer",
    "ensure_root",
    "enable_monitor_mode",
    "get_interface_channel",
    "get_interface_mode",
    "get_wireless_interfaces",
    "interface_supports_monitor_mode",
    "set_interface_channel",
]
