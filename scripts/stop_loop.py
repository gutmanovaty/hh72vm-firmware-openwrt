#!/usr/bin/env python3
"""Catch router boot window, disable S99unifi-openwrt, and run uow with full trace."""

import subprocess
import sys
import time

SSH_OPTS = [
    "ssh",
    "-o", "KexAlgorithms=curve25519-sha256",
    "-o", "HostKeyAlgorithms=+ssh-rsa",
    "-o", "PubkeyAcceptedKeyTypes=+ssh-rsa",
    "-o", "Ciphers=aes128-ctr",
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=NUL",
    "-o", "ConnectTimeout=3",
    "root@192.168.1.199",
]

def main():
    print("[*] Waiting for router port 22...")
    for i in range(120):
        res = subprocess.run(
            [*SSH_OPTS, "rm -f /etc/rc.d/S99unifi-openwrt; killall uow 2>/dev/null; /etc/init.d/unifi-openwrt stop 2>/dev/null; uptime"],
            capture_output=True,
            timeout=5
        )
        if res.returncode == 0:
            print("[+] Router online! Autostart disabled.")
            print(res.stdout.decode("utf-8", "replace"))
            return 0
        time.sleep(1)
    print("[-] Timeout waiting for router")
    return 1

if __name__ == "__main__":
    sys.exit(main())
