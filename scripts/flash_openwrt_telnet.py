#!/usr/bin/env python3
"""Install OpenWrt onto HH71VM/HH72VM via stock Telnet and /bin/fwupg."""

import argparse
import hashlib
import os
import socket
import sys
import time

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPTS_DIR)
FLASH_TOOLS_DIR = os.path.join(REPO_ROOT, "hh71vm-openwrt", "tools", "flash")
sys.path.insert(0, FLASH_TOOLS_DIR)
sys.path.insert(0, SCRIPTS_DIR)

import flash_openwrt_vendor  # noqa: E402
import inspect_hh72  # noqa: E402
import install_openwrt_lan  # noqa: E402
import tftp_dump_mtd  # noqa: E402

UPLOAD_PORT = 9999


def check_no_jrd_leftovers(tc):
    """Ensure /tmp/jrd-resource* and /tmp/ipq are absent before running fwupg."""
    for path in ("/tmp/jrd-resource-jffs2.img", "/tmp/jrd-resource", "/tmp/ipq"):
        out = tc.cmd(
            f"test -e {path} && echo 'LF_'FOUND || echo 'LF_'ABSENT"
        ).decode("latin1", errors="replace")
        if "LF_FOUND" in out:
            raise RuntimeError(f"Dangerous leftover found on router: {path}")
        if "LF_ABSENT" not in out:
            raise RuntimeError(f"Unclear check for {path}: {out!r}")


def upload_fw_via_inetd(tc, router_ip, local_ip, data):
    """Stream firmware bytes into /tmp/fw.bin over TCP using busybox inetd + dd."""
    local_md5 = hashlib.md5(data).hexdigest()

    # Check if /tmp/fw.bin is already present with matching size and MD5
    existing_md5 = tc.md5("/tmp/fw.bin")
    if existing_md5 == local_md5:
        print(f"/tmp/fw.bin already on router with matching MD5 ({local_md5})")
        return

    tc.cmd("rm -f /tmp/fw.bin /tmp/inetd_fw.conf", max_wait=10.0)
    conf_line = f"{UPLOAD_PORT} stream tcp nowait root /bin/dd dd of=/tmp/fw.bin bs=65536"
    tc.cmd(
        f"echo '{conf_line}' > /tmp/inetd_fw.conf && inetd /tmp/inetd_fw.conf",
        max_wait=10.0,
    )
    time.sleep(0.5)

    t0 = time.time()
    sock = socket.create_connection(
        (router_ip, UPLOAD_PORT),
        timeout=30,
        source_address=(local_ip, 0),
    )
    try:
        sock.sendall(data)
    finally:
        sock.close()
    elapsed = time.time() - t0
    time.sleep(1.0)

    tc.cmd("rm -f /tmp/inetd_fw.conf", max_wait=10.0)

    size_out = tc.cmd("wc -c < /tmp/fw.bin", max_wait=15.0).decode(
        "latin1", errors="replace"
    )
    nums = [int(tok) for tok in size_out.split() if tok.isdigit()]
    remote_size = nums[0] if nums else -1
    if remote_size != len(data):
        raise RuntimeError(
            f"/tmp/fw.bin size mismatch: router has {remote_size}, expected {len(data)}"
        )
    print(f"Uploaded {remote_size} bytes to /tmp/fw.bin in {elapsed:.2f}s")

    remote_md5 = tc.md5("/tmp/fw.bin")
    if remote_md5 != local_md5:
        raise RuntimeError(
            f"/tmp/fw.bin MD5 mismatch: router has {remote_md5}, expected {local_md5}"
        )
    print(f"Verified /tmp/fw.bin MD5 on router: {remote_md5}")


def wait_for_router_and_enable_telnet(args):
    """Wait up to 90s for router Wi-Fi boot, then ensure Telnet is open."""
    print(f"Waiting for router {args.router_ip} to finish booting on {args.interface}...")
    deadline = time.time() + 90.0
    local_ip = None
    while time.time() < deadline:
        try:
            local_ip = inspect_hh72.ensure_wifi_connected(
                router_ip=args.router_ip,
                interface=args.interface,
                profile_index=args.profile_index,
            )
            break
        except Exception:
            time.sleep(3.0)

    if not local_ip:
        raise RuntimeError(f"Router {args.router_ip} did not become reachable within 90s")

    print(f"Connected to {args.router_ip} via {args.interface} ({local_ip})")
    active_port = inspect_hh72.wait_for_telnet(
        args.router_ip, local_ip, ports=(args.telnet_port, 23), timeout=2.0
    )
    if active_port:
        return local_ip, active_port

    print("Enabling Telnet and INPUT accept via WebAPI...")
    client = inspect_hh72.WebApiClient(args.router_ip, local_ip)
    client.login("admin", args.password)
    orig_settings = None
    try:
        sys_settings = client.call("GetSystemSettings")
        orig_settings = sys_settings.get("result", {})
        for cmd in (
            f"telnetd -p {args.telnet_port} -l /bin/sh",
            "telnetd -l /bin/sh",
            "iptables -I INPUT -j ACCEPT",
        ):
            inspect_hh72.send_ntp_command(client, orig_settings, cmd)
            time.sleep(1.0)
        active_port = inspect_hh72.wait_for_telnet(
            args.router_ip, local_ip, ports=(args.telnet_port, 23), timeout=5.0
        )
    finally:
        if orig_settings is not None:
            try:
                client.call("SetSystemSettings", orig_settings)
            except Exception:
                pass
        client.logout()

    if not active_port:
        raise RuntimeError("Failed to open Telnet port after router boot")
    return local_ip, active_port


def main():
    """Verify backup and image, upload to /tmp/fw.bin, run fwupg check, and optionally fwupg reboot."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image",
        default=os.path.join(
            REPO_ROOT,
            "hh71vm-openwrt-flash-bundle",
            "firmware",
            "openwrt-rtkmipsel-rtl8197f-hh71vm-fwupg.bin",
        ),
    )
    parser.add_argument(
        "--backup-dir",
        default=os.path.join(REPO_ROOT, "backup-stock"),
    )
    parser.add_argument("--router-ip", default="10.0.3.1")
    parser.add_argument("--interface", default="Wi-Fi 3")
    parser.add_argument("--profile-index", type=int, default=0)
    parser.add_argument("--password", default="admin")
    parser.add_argument("--telnet-port", type=int, default=2323)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    data, plan = flash_openwrt_vendor.build_vendor_plan(args.image)
    flash_openwrt_vendor.print_vendor_plan(args.image, data, plan, args.dry_run)

    print()
    print("Verifying 16 MiB stock backup before touching router...")
    install_openwrt_lan.verify_backup(args.backup_dir)

    local_ip, active_port = wait_for_router_and_enable_telnet(args)
    print(f"Telnet active on {args.router_ip}:{active_port}")

    sock = socket.create_connection(
        (args.router_ip, active_port),
        timeout=10,
        source_address=(local_ip, 0),
    )
    tc = tftp_dump_mtd.TelnetControl.__new__(tftp_dump_mtd.TelnetControl)
    tc.sock = sock
    tc.sock.settimeout(2.0)
    time.sleep(0.5)
    tc._drain()

    try:
        install_openwrt_lan.check_stock_layout(tc)
        check_no_jrd_leftovers(tc)
        print("Verified absence of /tmp/jrd-resource* and /tmp/ipq leftovers.")

        upload_fw_via_inetd(tc, args.router_ip, local_ip, data)

        print("Running: fwupg check file /tmp/fw.bin ...")
        check_out = tc.cmd("fwupg check file /tmp/fw.bin", max_wait=60.0).decode(
            "latin1", errors="replace"
        )
        print(check_out)
        if "Firmware upgrade check OK!" not in check_out:
            raise RuntimeError(
                "'fwupg check' did not return 'Firmware upgrade check OK!'"
            )
        print("SUCCESS: 'fwupg check file /tmp/fw.bin' passed!")

        if args.dry_run:
            print("DRY RUN complete: /tmp/fw.bin is staged and verified on the router.")
            return 0

        if not args.yes:
            raise RuntimeError("Pass --yes to execute 'fwupg reboot file /tmp/fw.bin'")

        print("Executing: fwupg reboot file /tmp/fw.bin ...")
        tc.sock.sendall(b"fwupg reboot file /tmp/fw.bin\r\n")
        time.sleep(2.0)
        try:
            out = tc._drain(wait=5.0).decode("latin1", errors="replace")
            if out.strip():
                print(out)
        except OSError:
            pass
        print(
            "fwupg reboot triggered! First boot takes ~2 minutes while rootfs_data is formatted."
        )
        return 0
    finally:
        tc.close()


if __name__ == "__main__":
    sys.exit(main())
