#!/usr/bin/env python3
"""Deploy the cross-compiled uow-mipsel daemon and service files to HH72VM OpenWrt."""

import argparse
import os
import subprocess
import sys

import inspect_hh72

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPTS_DIR)
UOW_DIR = os.path.join(REPO_ROOT, "unifi-openwrt")

SSH_OPTS = [
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
    "ConnectTimeout=10",
]

INIT_SCRIPT = """#!/bin/sh /etc/rc.common
# unifi-openwrt: this OpenWrt AP as a UniFi AP (inform, adoption, settings).

START=99
STOP=10
USE_PROCD=1
PROG=/tmp/uow
GZIP_BIN=/etc/unifi-openwrt/uow.gz
STATE=/etc/unifi-openwrt/state

ensure_binary() {
\tif [ ! -x "$PROG" ]; then
\t\tzcat "$GZIP_BIN" > "${PROG}.$$"
\t\tchmod 755 "${PROG}.$$"
\t\tmv -f "${PROG}.$$" "$PROG"
\t\tln -sf "$PROG" /usr/bin/uow
\tfi
}

start_service() {
\tconfig_load unifi-openwrt
\tlocal inform_every hw_caps mesh_uplink enabled model inform_url hostname apply profile_caps locate_beep ssh_port led_idle uplink_port
\tconfig_get_bool enabled main enabled 0
\t[ "$enabled" = 1 ] || { echo "unifi-openwrt disabled (uci set unifi-openwrt.main.enabled=1)"; return 0; }
\tensure_binary
\tconfig_get model main model 'U7PG2'
\tconfig_get inform_url main inform_url 'http://192.168.1.2:8080/inform'
\tlocal console_ip="${inform_url#*://}"
\tconsole_ip="${console_ip%%:*}"
\tconsole_ip="${console_ip%%/*}"
\tconfig_get hostname main hostname "$(uci -q get system.@system[0].hostname)"
\tconfig_get_bool apply main apply 1
\tconfig_get_bool profile_caps main profile_caps 1
\tconfig_get_bool locate_beep main locate_beep 1
\tconfig_get ssh_port main ssh_port 2222
\tconfig_get_bool mesh_uplink main mesh_uplink 0
\tconfig_get hw_caps main hw_caps 0
\tconfig_get inform_every main inform_every 0
\tconfig_get led_idle main led_idle ''
\tconfig_get uplink_port main uplink_port ''
\tmkdir -p "$STATE"; chmod 700 /etc/unifi-openwrt "$STATE"

\tprocd_open_instance
\tprocd_set_param command "$PROG" -ap local \\
\t\t-mac "$(cat /sys/class/net/br-lan/address)" \\
\t\t-model "$model" -hostname "${hostname:-HH72VM}" -url "$inform_url" -console "$console_ip" -state "$STATE"
\tprocd_set_param respawn 3600 10 5
\tprocd_set_param stdout 1
\tprocd_set_param stderr 1
\tprocd_close_instance
}

service_triggers() {
\tprocd_add_reload_trigger unifi-openwrt
}
"""


def ssh_run(host, script, stdin_bytes=None):
    """Execute a shell script on the OpenWrt router via SSH."""
    cmd = ["ssh", *SSH_OPTS, f"root@{host}", "sh"]
    input_data = script.encode("utf-8") if stdin_bytes is None else stdin_bytes
    res = subprocess.run(cmd, input=input_data, capture_output=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(
            f"SSH command failed ({res.returncode}): {res.stderr.decode('utf-8', 'replace')}"
        )
    return res.stdout.decode("utf-8", "replace")


def ssh_upload(host, remote_path, content_bytes, mode="0644"):
    """Stream content_bytes to remote_path on the router via SSH."""
    cmd = [
        "ssh",
        *SSH_OPTS,
        f"root@{host}",
        f"cat > {remote_path} && chmod {mode} {remote_path}",
    ]
    res = subprocess.run(cmd, input=content_bytes, capture_output=True, timeout=60)
    if res.returncode != 0:
        raise RuntimeError(
            f"Upload to {remote_path} failed: {res.stderr.decode('utf-8', 'replace')}"
        )


def main():
    """Upload uow.gz, init.d script, and UCI config, then test and start uow."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.199")
    parser.add_argument("--controller-ip", default="192.168.1.2")
    parser.add_argument("--inform-port", type=int, default=8080)
    parser.add_argument("--model", default="U7PG2")
    parser.add_argument("--hostname", default="Alcatel-HH72VM")
    parser.add_argument("--apply", default="0")
    args = parser.parse_args()

    gz_path = os.path.join(UOW_DIR, "dist", "openwrt", "bin", "uow-mipsel.gz")
    if not os.path.exists(gz_path):
        raise SystemExit(f"Missing {gz_path}; build uow-mipsel first.")

    with open(gz_path, "rb") as fh:
        gz_bytes = fh.read()

    cfg_path = os.path.join(UOW_DIR, "packaging", "files", "etc", "config", "unifi-openwrt")
    with open(cfg_path, "rb") as fh:
        cfg_bytes = fh.read().replace(b"\r\n", b"\n")

    print(f"[1/4] Creating /etc/unifi-openwrt on {args.host} and uploading uow.gz ({len(gz_bytes)} B)...")
    ssh_run(args.host, "mkdir -p /etc/unifi-openwrt/state && chmod 700 /etc/unifi-openwrt /etc/unifi-openwrt/state\n")
    ssh_upload(args.host, "/etc/unifi-openwrt/uow.gz", gz_bytes, mode="0644")

    print("[2/4] Extracting /tmp/uow and installing /etc/init.d/unifi-openwrt...")
    ssh_upload(
        args.host,
        "/etc/init.d/unifi-openwrt",
        INIT_SCRIPT.replace("\r\n", "\n").encode("utf-8"),
        mode="0755",
    )
    ssh_run(
        args.host,
        "zcat /etc/unifi-openwrt/uow.gz > /tmp/uow && chmod 755 /tmp/uow && ln -sf /tmp/uow /usr/bin/uow\n",
    )

    print("[3/4] Running 'uow -ap local -suggest' on router to verify hardware detection...")
    suggest_out = ssh_run(args.host, "/usr/bin/uow -ap local -suggest\n")
    print(suggest_out)

    print(f"[4/4] Configuring /etc/config/unifi-openwrt -> http://{args.controller_ip}:{args.inform_port}/inform...")
    ssh_upload(args.host, "/etc/config/unifi-openwrt", cfg_bytes, mode="0644")
    inform_url = f"http://{args.controller_ip}:{args.inform_port}/inform"
    uci_script = f"""
uci set system.@system[0].hostname='{args.hostname}'
uci commit system
uci set unifi-openwrt.main.enabled='1'
uci set unifi-openwrt.main.model='{args.model}'
uci set unifi-openwrt.main.hostname='{args.hostname}'
uci set unifi-openwrt.main.inform_url='{inform_url}'
uci set unifi-openwrt.main.apply='{args.apply}'
uci set unifi-openwrt.main.profile_caps='1'
uci set unifi-openwrt.main.uplink_port='eth0'
uci commit unifi-openwrt
/etc/init.d/unifi-openwrt enable
/etc/init.d/unifi-openwrt restart
sleep 6
logread | grep uow | tail -n 30
"""
    logs = ssh_run(args.host, uci_script)
    print("=== uow service logs ===")
    print(inspect_hh72.redact_sensitive(logs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
