# hh72vm-firmware-openwrt

OpenWrt port, UniFi integration notes, scripts, and complete source tree for the **Alcatel LINKHUB HH72VM (`HH72VM-2BALAT3`, board `HH72-V-V2.0`)**.

---

## Overview

This repository provides full documentation, custom utilities, and complete source code to:
1. **Flash OpenWrt** onto the Alcatel LINKHUB HH72VM (Realtek RTL8197FS + RTL8812F + Qualcomm MDM9645 LTE).
2. **Integrate with UniFi Network:** Run the lightweight `unifi-openwrt` (`uow`) daemon emulating a UniFi AP (`U7PG2` / AP-AC-Pro), supporting native Dropbear SSH adoption via `/usr/bin/syswrapper.sh`, Inform L3 telemetry, and broadcasting unified UniFi SSIDs across both 2.4 GHz and 5 GHz radios.

For a complete step-by-step guide from stock backup to full UniFi Controller adoption, see:
👉 **[docs/tutorial-hh72-openwrt-unifi.md](docs/tutorial-hh72-openwrt-unifi.md)**

---

## Upstream Credits & Attribution

This project is built upon the invaluable contributions of the open-source community:

- **HH71VM OpenWrt Port:** [`sowarden/hh71vm-openwrt`](https://github.com/sowarden/hh71vm-openwrt) by **sowarden**
  - Linux 4.14 kernel port, Realtek RTL8197FS SoC support, `rtl8192cd`/`rtl8812f` wireless drivers, `hh71vm-modemd` LTE daemon, and LuCI web interface.
- **UniFi OpenWrt Daemon (`uow`):** [`antoniocosta/unifi-openwrt`](https://github.com/antoniocosta/unifi-openwrt) by **Antonio Costa**
  - UniFi L3 Inform protocol implementation and configuration generators.

---

## Hardware Specifications

| Property | Value |
|---|---|
| Model / SKU | Alcatel LINKHUB `HH72VM-2BALAT3` |
| Mainboard | `HH72-V-V2.0` |
| SoC | Realtek RTL8197FS (MIPS 24Kc @ 500 MHz, softfloat) |
| System Memory | 128 MB DDR2 |
| Flash | 16 MB SPI NOR (`m25p80`) |
| Cellular Modem | Qualcomm Snapdragon X12 (MDM9645), LTE Cat.7 |
| Ethernet | 1x Gigabit RJ45 (RTL8211F PHY) |
| Wi-Fi 2.4 GHz | Integrated RTL8197FS 2T2R 802.11b/g/n (`rtl8192cd`) |
| Wi-Fi 5 GHz | PCIe Realtek RTL8812F 2T2R 802.11a/n/ac |

See [docs/hardware-status.md](docs/hardware-status.md) for full low-level hardware verification logs.

---

## Repository Structure

- `docs/`
  - `tutorial-hh72-openwrt-unifi.md`: Complete flashing, networking, and UniFi adoption guide.
  - `hardware-status.md`: Detailed hardware registers, memory map, and probe logs.
- `scripts/`: Diagnostic, flashing, TFTP backup, and deployment automation tools.
- `bin/`: Pre-compiled and optimized `uow-mipsel.gz` binary tailored for RTL8197FS MIPS softfloat.
- `hh71vm-openwrt/`: Complete upstream OpenWrt build tree and feeds for the platform.
- `unifi-openwrt/`: Source tree of the UniFi OpenWrt daemon.

---

## Remotes

Mirrored across GitHub and GitLab:
- GitHub: `https://github.com/gutmanovaty/hh72vm-firmware-openwrt`
- GitLab: `https://g.gut.red/gut.red/hh72vm-firmware-openwrt`
