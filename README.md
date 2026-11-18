# hh72vm-firmware-openwrt

OpenWrt port and UniFi integration notes, scripts, and custom builds for the **Alcatel LINKHUB HH72VM (`HH72VM-2BALAT3`)**.

## Goals

1. **OpenWrt on HH72VM-2BALAT3:** Verify hardware compatibility with [`sowarden/hh71vm-openwrt`](https://github.com/sowarden/hh71vm-openwrt), take a full 16 MiB Realtek SPI flash backup over Telnet + TFTP, and flash/adapt OpenWrt for the `HH72-V-V2.0` board.
2. **UniFi Integration (`unifi-openwrt`):** Adapt [`antoniocosta/unifi-openwrt`](https://github.com/antoniocosta/unifi-openwrt) (`uow`) for OpenWrt 19.07 / `rtkmipsel` (`rtl8192cd` Wi-Fi driver) so the router can be adopted as a UniFi Access Point while optionally providing LTE failover WAN via VLAN on its single RJ45 port.

## Target Hardware Summary

| Property | Observed Value |
|---|---|
| Marketing / SKU | Alcatel LINKHUB `HH72VM-2BALAT3` |
| WebUI `DeviceName` | `HUB72` |
| `HwVersion` | `HH72-V-V2.0` |
| `SwVersion` / Modem | `HH72_E4_02.01_05` |
| WebUI `projectName` (`dist/build.js`) | `HH71` |
| Wired Ethernet | 1x RJ45 LAN/WAN port |

See [docs/hardware-status.md](docs/hardware-status.md) for detailed probe status and verification steps.

## Remotes

This repository is mirrored across GitLab and GitHub:
- GitLab: `https://g.gut.red/gut.red/hh72vm-firmware-openwrt`
- GitHub: `https://github.com/gutmanovaty/hh72vm-firmware-openwrt`
