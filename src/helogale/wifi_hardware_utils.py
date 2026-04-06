import getpass
import os
import subprocess
import re

def get_wireless_interfaces():
    """Return a list of wireless interface names."""
    result = subprocess.run(["iw", "dev"], capture_output=True, text=True)
    interfaces = re.findall(r"Interface\s+(\w+)", result.stdout)
    return interfaces

def _interfaces_by_phy():
    result = subprocess.run(["iw", "dev"], capture_output=True, text=True)
    interfaces = {}
    current_phy = None

    for line in result.stdout.splitlines():
        phy_match = re.match(r"^phy#(\d+)", line)
        if phy_match:
            current_phy = phy_match.group(1)
            continue

        iface_match = re.search(r"Interface\s+(\S+)", line)
        if iface_match and current_phy is not None:
            interfaces[iface_match.group(1)] = current_phy

    return interfaces


def get_interface_mode(interface):
    """Return the current mode of a wireless interface, or None if unknown."""
    result = subprocess.run(["iw", "dev", interface, "info"], capture_output=True, text=True)
    if result.returncode != 0:
        return None

    match = re.search(r"^\s*type\s+(\w+)$", result.stdout, re.MULTILINE)
    return match.group(1).lower() if match else None


def interface_is_monitor_mode(interface):
    """Return True when the interface is currently in monitor mode."""
    return get_interface_mode(interface) == "monitor"


def get_interface_channel(interface):
    """Return the current channel for a wireless interface, or None if unknown."""
    result = subprocess.run(["iw", "dev", interface, "info"], capture_output=True, text=True)
    if result.returncode != 0:
        return None

    match = re.search(r"^\s*channel\s+(\d+)", result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else None


def set_interface_channel(interface, channel, verbose=False):
    """Set the channel for a wireless interface."""
    command = ["iw", "dev", interface, "set", "channel", str(channel)]
    if os.geteuid() == 0:
        result = subprocess.run(command, capture_output=True, text=True)
    else:
        password = getpass.getpass("Root password: ")
        result = _run_command_as_root(command, password, verbose=verbose)

    if result.returncode != 0 and verbose:
        print(f"Error setting channel on {interface}: {' '.join(command)}")
        print(f"Error output: {result.stderr.strip()}")
    return result.returncode == 0


def _run_command_as_root(cmd, password, verbose=False):
    sudo_cmd = ["sudo", "-S", "-p", "", *cmd]
    result = subprocess.run(
        sudo_cmd,
        input=password + "\n",
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and verbose:
        print(f"Error occurred while running command: {' '.join(cmd)}")
        print(f"Error output: {result.stderr.strip()}")
    return result


def enable_monitor_mode(interface, verbose=False):
    """Switch a wireless interface into monitor mode.

    Returns True when the interface was successfully switched, False otherwise.
    """
    if interface not in get_wireless_interfaces():
        if verbose:
            print(f"Interface {interface} is not a wireless interface.")
        return False

    password = None
    if os.geteuid() != 0:
        password = getpass.getpass("Root password: ")

    commands = [
        ["ip", "link", "set", interface, "down"],
        ["iw", "dev", interface, "set", "type", "monitor"],
        ["ip", "link", "set", interface, "up"],
    ]

    for cmd in commands:
        if os.geteuid() == 0:
            result = subprocess.run(cmd, capture_output=True, text=True)
        else:
            result = _run_command_as_root(cmd, password, verbose=verbose)

        if result.returncode != 0:
            return False

    return True


def interface_supports_monitor_mode():
    """Return a dict of interface -> True/False for monitor mode support."""
    result = subprocess.run(["iw", "list"], capture_output=True, text=True)
    list_output = result.stdout
    blocks = list_output.split("Wiphy")  # split per radio

    support = {}
    interfaces = _interfaces_by_phy()

    for block in blocks[1:]:
        phy_match = re.match(r"^\s*(\d+)", block)
        phy = phy_match.group(1) if phy_match else None

        modes = re.findall(r"^\s*\*\s+(.+)$", block, re.MULTILINE)
        modes = [mode.strip().lower() for mode in modes]
        phy_supports_monitor = "monitor" in modes

        if phy is not None:
            for iface, iface_phy in interfaces.items():
                if iface_phy == phy:
                    support[iface] = phy_supports_monitor

    if not support:
        has_monitor = bool(re.search(r"^\s*\*\s+monitor\s*$", list_output, re.MULTILINE | re.IGNORECASE))
        for iface in get_wireless_interfaces():
            support[iface] = has_monitor

    return support

if __name__ == "__main__":
    interfaces = get_wireless_interfaces()
    print("Detected wireless interfaces:", interfaces)

    support = interface_supports_monitor_mode()
    for iface, can_monitor in support.items():
        print(f"{iface}: monitor mode supported = {can_monitor}")
