# HH72VM-2BALAT3 Hardware Verification Status

## 1. Stock WebUI & API Inspection

Captured from the stock web interface (`GoAhead-Webs PeerSec-MatrixSSL`, `/jrd/webapi` `GetSystemInfo` and `/dist/build.js`):

- **DeviceName / Model:** `HUB72` (Help link project `HH72`)
- **Hardware Version (`HwVersion`):** `HH72-V-V2.0`
- **Software Version (`SwVersionMain` / `SwVersion`):** `HH72_E4_02.01_05`
- **Modem Version:** `HH72_E4_02.01_05`
- **AppVersion:** `V1.0`
- **HttpApiVersion:** `TCL-HTTP`
- **WebUI `projectName` (`dist/build.js`):** `HH71`

All device-unique identifiers (IMEI, IMSI, ICCID, MSISDN, MAC addresses) are redacted.

## 2. Upstream Reference Bundle

- Bundle: `hh71vm-openwrt-flash-bundle.zip` (`sowarden/hh71vm-openwrt`)
- Verified release tag: `hh71vm-r00000000037597446324-a000001-201b0e1782b0`
- Bundle SHA-256: `314CD8160310CE45A00ED8D816DEDA7B98F4DC1D7054F1980E678E1B24D947E6`

## 3. Pending Hardware Checks (via Stock Telnet)

Before flashing SPI flash, the following markers must be verified against the `HH71VM` reference layout:

- [ ] `/proc/cpuinfo` (`RTL8197FS`)
- [ ] `/proc/mtd` (expected stock 3+9+4 MiB layout: `mtd0` 3 MiB, `mtd1` 9 MiB, `mtd2` 4 MiB)
- [ ] `dmesg` RF/SoC markers (`Bonding`, `RFE type`, `PHY_REG_PG`, `chip_version`, `hwsetting`)
- [ ] `/proc/wlan*` and `/proc/rtl865x/port_status`
- [ ] `/jffs2/bin/oem_start.sh` (Telnet startup condition)
