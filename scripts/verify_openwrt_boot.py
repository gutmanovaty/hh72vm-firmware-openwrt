#!/usr/bin/env python3
"""Wait for OpenWrt first boot on HH72VM, connect Wi-Fi 3, and verify SSH/LuCI."""

import os
import socket
import subprocess
import sys
import tempfile
import time

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)

import inspect_hh72  # noqa: E402

OPENWRT_IP = "192.168.1.1"
OPENWRT_SSIDS = ("HH71VM-5G", "HH71VM")
OPENWRT_WIFI_KEY = "hh71vm12345"

WLAN_PROFILE_XML = """<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig>
        <SSID>
            <name>{ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>WPA2PSK</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>{key}</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>
"""


def install_wlan_profiles(interface="Wi-Fi 3"):
    """Register HH71VM-5G and HH71VM WLAN profiles on Windows."""
    for ssid in OPENWRT_SSIDS:
        xml_content = WLAN_PROFILE_XML.format(ssid=ssid, key=OPENWRT_WIFI_KEY)
        with tempfile.NamedTemporaryFile(
            "w", suffix=".xml", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(xml_content)
            xml_path = tf.name
        try:
            subprocess.run(
                [
                    "netsh",
                    "wlan",
                    "add",
                    "profile",
                    f"filename={xml_path}",
                    f"interface={interface}",
                ],
                capture_output=True,
                check=False,
            )
        finally:
            try:
                os.remove(xml_path)
            except OSError:
                pass


def try_connect_openwrt_wifi(interface="Wi-Fi 3"):
    """Scan on interface and connect to HH71VM-5G or HH71VM if visible."""
    out = subprocess.check_output(
        ["netsh", "wlan", "show", "networks", f"interface={interface}"],
        encoding="oem",
        errors="replace",
    )
    for ssid in OPENWRT_SSIDS:
        if ssid in out:
            subprocess.run(
                [
                    "netsh",
                    "wlan",
                    "connect",
                    f"name={ssid}",
                    f"interface={interface}",
                ],
                capture_output=True,
                check=False,
            )
            return ssid
    return None


def run_ssh_cmd(host, remote_cmd):
    """Run a command on OpenWrt via ssh with legacy ssh-rsa enabled."""
    cmd = [
        "ssh",
        "-o",
        "HostKeyAlgorithms=+ssh-rsa",
        "-o",
        "PubkeyAcceptedKeyTypes=+ssh-rsa",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=NUL",
        "-o",
        "ConnectTimeout=10",
        f"root@{host}",
        remote_cmd,
    ]
    res = subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return res.returncode, res.stdout + res.stderr


def main():
    """Wait up to 240s for OpenWrt first boot, then collect board & radio status."""
    install_wlan_profiles("Wi-Fi 3")
    print(
        "Waiting for OpenWrt first boot (fwd flash write + rootfs_data erase takes ~2-3 min)..."
    )
    t0 = time.time()
    deadline = t0 + 240.0
    while time.time() < deadline:
        elapsed = int(time.time() - t0)
        if inspect_hh72.probe_tcp(OPENWRT_IP, 22, timeout=1.5) or inspect_hh72.probe_tcp(
            OPENWRT_IP, 80, timeout=1.5
        ):
            print(f"[{elapsed}s] OpenWrt is reachable at {OPENWRT_IP}!")
            break

        ssid = try_connect_openwrt_wifi("Wi-Fi 3")
        if ssid:
            print(f"[{elapsed}s] Saw OpenWrt Wi-Fi ({ssid}), associating...")
        else:
            print(f"[{elapsed}s] Still writing/booting...")
        time.sleep(5.0)
    else:
        raise RuntimeError(f"OpenWrt did not come up at {OPENWRT_IP} within 240s")

    time.sleep(2.0)
    remote_script = (
        "ubus call system board; "
        "cat /etc/openwrt_release; "
        "cat /proc/mtd; "
        "iwinfo; "
        "ip addr show br-lan; "
        "ip addr show eth2 2>/dev/null || true"
    )
    rc, output = run_ssh_cmd(OPENWRT_IP, remote_script)
    redacted = inspect_hh72.redact_sensitive(output)
    print(f"SSH exit code: {rc}")
    print(redacted)

    out_path = os.path.join(REPO_ROOT, "openwrt-boot-verified.raw.txt")
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(redacted)
    return 0


if __name__ == "__main__":
    sys.exit(main())
