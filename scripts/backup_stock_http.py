#!/usr/bin/env python3
"""Take and verify the 16 MiB stock SPI flash backup over Telnet + HTTP."""

import argparse
import hashlib
import http.client
import json
import os
import shutil
import socket
import sys
import time

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPTS_DIR)
FLASH_TOOLS_DIR = os.path.join(REPO_ROOT, "hh71vm-openwrt", "tools", "flash")
sys.path.insert(0, FLASH_TOOLS_DIR)
sys.path.insert(0, SCRIPTS_DIR)

import inspect_hh72  # noqa: E402
import install_openwrt_lan  # noqa: E402
import tftp_dump_mtd  # noqa: E402

WEB_STAGE_PATH = "/tmp/webrc/www/dist/dump.ico"
WEB_URL_PATH = "/dist/dump.ico"
MAX_RETRIES = 3


def http_download(router_ip, local_ip, url_path):
    """Download a binary payload from the router's HTTP server over local_ip."""
    conn = http.client.HTTPConnection(
        router_ip,
        80,
        timeout=60,
        source_address=(local_ip, 0),
    )
    try:
        conn.request("GET", url_path)
        resp = conn.getresponse()
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status} for {url_path}")
        return resp.read()
    finally:
        conn.close()


def dump_partition_http(tc, router_ip, local_ip, devname, size, label, outdir):
    """Dump one MTD partition via /tmp/webrc/www and verify size and MD5."""
    remote_dev = f"/dev/{devname}"
    outfile = os.path.join(outdir, f"{devname}-{label}.bin")
    best_effort = None

    for attempt in range(1, MAX_RETRIES + 1):
        print(f"[{devname}] attempt {attempt}/{MAX_RETRIES}: md5sum before...")
        md5_before = tc.md5(remote_dev)
        print(f"[{devname}] device md5 (before) = {md5_before}")

        t0 = time.time()
        try:
            tc.cmd(f"dd if={remote_dev} of={WEB_STAGE_PATH} bs=65536", max_wait=30.0)
            data = http_download(router_ip, local_ip, WEB_URL_PATH)
        finally:
            tc.cmd(f"rm -f {WEB_STAGE_PATH}", max_wait=10.0)
        elapsed = time.time() - t0

        md5_after = tc.md5(remote_dev)
        print(f"[{devname}] device md5 (after)  = {md5_after}")

        local_md5 = hashlib.md5(data).hexdigest()
        size_ok = len(data) == size
        md5_ok = local_md5 in (md5_before, md5_after)

        print(
            f"[{devname}] received {len(data)} bytes in {elapsed:.2f}s, "
            f"local_md5={local_md5}, size_ok={size_ok}, md5_ok={md5_ok}"
        )

        if size_ok and md5_ok:
            with open(outfile, "wb") as fh:
                fh.write(data)
            return outfile, local_md5, False

        if size_ok and md5_before != md5_after:
            best_effort = (data, local_md5)
            print(f"[{devname}] mounted partition changed during read; keeping snapshot fallback")
            continue

    if best_effort is not None:
        data, local_md5 = best_effort
        with open(outfile, "wb") as fh:
            fh.write(data)
        print(f"[{devname}] saved verified snapshot fallback, md5={local_md5}")
        return outfile, local_md5, True

    raise RuntimeError(f"{devname}: failed to dump cleanly after {MAX_RETRIES} attempts")


def main():
    """Dump mtd0, mtd1, mtd2 into backup-stock and run install_openwrt_lan.verify_backup."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--router-ip", default="10.0.3.1")
    parser.add_argument("--interface", default="Wi-Fi 3")
    parser.add_argument("--profile-index", type=int, default=0)
    parser.add_argument("--telnet-port", type=int, default=2323)
    parser.add_argument(
        "--backup-dir",
        default=os.path.join(REPO_ROOT, "backup-stock"),
    )
    args = parser.parse_args()

    local_ip = inspect_hh72.ensure_wifi_connected(
        router_ip=args.router_ip,
        interface=args.interface,
        profile_index=args.profile_index,
    )
    print(f"Connected to {args.router_ip} via {args.interface} ({local_ip})")

    os.makedirs(args.backup_dir, exist_ok=True)
    sock = socket.create_connection(
        (args.router_ip, args.telnet_port),
        timeout=10,
        source_address=(local_ip, 0),
    )
    tc = tftp_dump_mtd.TelnetControl.__new__(tftp_dump_mtd.TelnetControl)
    tc.sock = sock
    tc.sock.settimeout(2.0)
    time.sleep(0.5)
    tc._drain()

    checksums = {}
    try:
        install_openwrt_lan.check_stock_layout(tc)
        manifest = {
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            "source": "stock via telnet+http",
            "partitions": [],
        }
        for dev, size, label in install_openwrt_lan.STOCK_PARTITIONS:
            path, md5, unstable = dump_partition_http(
                tc, args.router_ip, local_ip, dev, size, label, args.backup_dir
            )
            with open(path, "rb") as fh:
                sha256 = hashlib.sha256(fh.read()).hexdigest()
            checksums[os.path.basename(path)] = sha256
            entry = {
                "dev": dev,
                "label": label,
                "size": size,
                "file": os.path.basename(path),
                "md5": md5,
            }
            if unstable:
                entry["unstable"] = True
            manifest["partitions"].append(entry)
    finally:
        tc.close()

    manifest_path = os.path.join(args.backup_dir, install_openwrt_lan.BACKUP_MANIFEST)
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1, ensure_ascii=False)

    sha_path = os.path.join(args.backup_dir, "SHA256SUMS.txt")
    with open(sha_path, "w", newline="", encoding="utf-8") as fh:
        for fname, sha in checksums.items():
            fh.write(f"{sha} *{fname}\n")

    install_openwrt_lan.verify_backup(args.backup_dir)

    bundle_backup_dir = os.path.join(
        REPO_ROOT, "hh71vm-openwrt-flash-bundle", "backup-stock"
    )
    if os.path.isdir(os.path.dirname(bundle_backup_dir)):
        if os.path.exists(bundle_backup_dir):
            shutil.rmtree(bundle_backup_dir)
        shutil.copytree(args.backup_dir, bundle_backup_dir)
        install_openwrt_lan.verify_backup(bundle_backup_dir)
        print(f"Mirrored verified backup to {bundle_backup_dir}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
