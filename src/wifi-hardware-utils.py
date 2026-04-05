import subprocess
import re

def get_wireless_interfaces():
    """Return a list of wireless interface names."""
    result = subprocess.run(["iw", "dev"], capture_output=True, text=True)
    interfaces = re.findall(r"Interface\s+(\w+)", result.stdout)
    return interfaces

def interface_supports_monitor_mode():
    """Return a dict of interface -> True/False for monitor mode support."""
    result = subprocess.run(["iw", "list"], capture_output=True, text=True)
    blocks = result.stdout.split("Wiphy")  # split per radio

    support = {}

    for block in blocks:
        iface_match = re.findall(r"Interface\s+(\w+)", block)
        if not iface_match:
            continue

        iface = iface_match[0]

        # Look for supported interface modes
        modes = re.findall(r"\*\s+(\w+)", block)

        support[iface] = "monitor" in modes

    return support

if __name__ == "__main__":
    interfaces = get_wireless_interfaces()
    print("Detected wireless interfaces:", interfaces)

    support = interface_supports_monitor_mode()
    for iface, can_monitor in support.items():
        print(f"{iface}: monitor mode supported = {can_monitor}")
