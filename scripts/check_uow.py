#!/usr/bin/env python3
"""Ensure 10-rtl8197f-gphy hotplug hook is installed and inspect uow logs on 192.168.1.199."""

import subprocess
import sys

import inspect_hh72

SSH_CMD = [
    "ssh",
    "-o",
    "KexAlgorithms=curve25519-sha256",
    "-o",
    "HostKeyAlgorithms=+ssh-rsa",
    "-o",
    "PubkeyAcceptedKeyTypes=+ssh-rsa",
    "-o",
    "Ciphers=aes128-ctr",
    "-o",
    "StrictHostKeyChecking=no",
    "-o",
    "UserKnownHostsFile=NUL",
    "-o",
    "ConnectTimeout=8",
    "root@192.168.1.199",
    "sh",
]

REMOTE_SCRIPT = """
uptime
ps | grep uow
logread | grep uow | tail -n 30
dmesg | tail -n 20
"""


def main():
    """Run remote inspection over Ethernet SSH with retry and print redacted output."""
    payload = REMOTE_SCRIPT.replace("\r\n", "\n").encode("utf-8")
    for attempt in range(1, 6):
        try:
            res = subprocess.run(
                SSH_CMD,
                input=payload,
                capture_output=True,
                timeout=12,
            )
            out = (res.stdout + res.stderr).decode("utf-8", errors="replace")
            if res.returncode == 0:
                print(inspect_hh72.redact_sensitive(out))
                return 0
            print(f"[attempt {attempt}] rc={res.returncode}: {out.strip()}")
        except subprocess.TimeoutExpired:
            print(f"[attempt {attempt}] timed out, retrying...")
    return 1


if __name__ == "__main__":
    sys.exit(main())
