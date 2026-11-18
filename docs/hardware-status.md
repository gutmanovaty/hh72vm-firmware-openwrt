# HH72VM-2BALAT3 Hardware Verification Status

## 1. Stock WebUI & API Inspection

Captured from the stock web interface (`GoAhead-Webs PeerSec-MatrixSSL`, `/jrd/webapi` `GetSystemInfo` and `/dist/build.js`):

- **DeviceName / Model:** `HUB72` (`HH72VM-2BALAT3`)
- **Hardware Version (`HwVersion`):** `HH72-V-V2.0`
- **Software Version (`SwVersionMain` / `SwVersion`):** `HH72_E4_02.01_05`
- **Modem Version:** `HH72_E4_02.01_05`
- **AppVersion:** `V1.0`
- **HttpApiVersion:** `TCL-HTTP`
- **WebUI `projectName` (`dist/build.js`):** `HH71`

All device-unique identifiers (IMEI, IMSI, ICCID, MSISDN, MAC addresses, serials) are redacted.

## 2. Upstream Reference Bundle

- Bundle: `hh71vm-openwrt-flash-bundle.zip` (`sowarden/hh71vm-openwrt`)
- Verified release tag: `hh71vm-r00000000037597446324-a000001-201b0e1782b0`
- Bundle SHA-256: `314CD8160310CE45A00ED8D816DEDA7B98F4DC1D7054F1980E678E1B24D947E6`

## 3. Verified Hardware Layout (via Stock Telnet)

All hardware markers on `HH72VM-2BALAT3` (`HH72-V-V2.0`) match the `HH71VM` reference platform bit-for-bit:

- [x] **Kernel (`/proc/version`):**
  `Linux version 3.10.90 (jianrong.wei@TctSwd) (gcc version 4.4.7 (Realtek MSDK-4.4.7 Build 2001) ) #1 Wed Nov 4 04:01:54 CST 2020`
- [x] **SoC (`/proc/cpuinfo` & `dmesg`):**
  `system type: RTL8197F` (`SoC: 8197FS`), `cpu model: MIPS 24Kc V8.5`, `BogoMIPS: 666.41`, `isa: mips1 mips2 mips32r2`, `ASEs implemented: mips16`
- [x] **SPI Flash Layout (`/proc/mtd` — `m25p80 spi0.0`, 16 MiB total, `erasesize: 0x1000`):**
  - `mtd0`: `00300000` (`boot+cfg+linux`, 3 MiB)
  - `mtd1`: `00900000` (`rootfs`, 9 MiB)
  - `mtd2`: `00400000` (`jffs2 file`, 4 MiB)
- [x] **Radio / RF Calibration Markers (`dmesg` & `/proc/wlan*`):**
  - **2.4 GHz (`wlan1`):**
    - `chip_version=0x100a, WlanSupportAbility = 0x3`
    - `[97F] Bonding Type 97FS, PKG1`
    - `[97F] RFE type 1 PHY paratemters: GPA0+GLNA0`
    - `[GetHwReg88XX][PHY_REG_PG_8197Fmp_Type1]`
    - `chipVersion: RTL8197FS MP B`, `MIMO_TR_hw_support: 2T2R`, `regdomain: 3`, `xcap: 39`, `ther: 38`
  - **5 GHz (`wlan0`):**
    - `chip_version=0x2001, WlanSupportAbility = 0x3`
    - `[GetHwReg88XX][PHY_REG_PG_8812Fmp_Type0]`
    - `[set_8812F_trx_regs] +++`
    - `regdomain: 3`
- [x] **Ethernet Switch & PHY (`dmesg` & `/proc/rtl865x/port_status`):**
  - `eth0 added. vid=9 Member port 0x10f...`
  - `eth1 added. vid=8 Member port 0x10...` (`[peth0] added, mapping to [eth1]`)
  - `extWrite phyId(6), pageId(3336), regId(17), regData:0x9`
  - `extWrite phyId(6), pageId(3336), regId(21), regData:0x19`
  - `extWrite phyId(6), pageId(0), regId(0), regData:0x1300`
  - `Port0`: `1G Duplex Enabled`, `CPUPort`: `1G Duplex Enabled`
- [x] **Internal LTE Modem Interconnect (`dmesg` & `/jffs2/bin/oem_start.sh`):**
  - `rndis_host 1-1:1.0 usb0: register 'rndis_host' at usb-rtl819x-ehci-1, RNDIS device`
  - Stock IP on `usb0`: `192.168.225.111`, gateway `192.168.225.1`
  - Exported GPIOs: `22`, `57`
- [x] **Stock Telnet Notes (`HH72_E4_02.01_05`):**
  - `GoAhead-Webs` requires `Referer` and `X-Requested-With: XMLHttpRequest` headers on `/jrd/webapi`.
  - In `SetSystemSettings`, `NtpServer1` uses a short C buffer and `/jrd-resource/bin/firewall_oem.sh` filters incoming ports; sending concise `;telnetd -p 2323 -l /bin/sh;` followed by `;iptables -I INPUT -j ACCEPT;` opens Telnet immediately without rebooting.
  - Persistent boot condition in `/jffs2/bin/oem_start.sh` checks `/jrd-resource/resource/jrdcfg/enable_telnet` and starts `telnetd -l /bin/sh`.

## 4. Verified 16 MiB Stock SPI Flash Backup (`install_openwrt_lan.py --dry-run`)

Captured and verified via `scripts/backup_stock_http.py` and `install_openwrt_lan.py --dry-run` (raw binary images are gitignored in `backup-stock/`):

| Partition | Label | Size | MD5 | SHA-256 |
|---|---|---|---|---|
| `mtd0` | `boot_cfg_linux` | `3,145,728` B (`0x300000`) | `65837916627ee53133d30cdbd352165f` | `9c0de4449d9d93b7952495ee9dcc79f965541ff9e46d3335317aab56c92af955` |
| `mtd1` | `rootfs` | `9,437,184` B (`0x900000`) | `f6f524f6bc6fa59b0751f6c9c943f5d2` | `7c1c4ebe1676254ec7893dd0178bf2ec1e2535d281ae37365e4cb3ea14d5c681` |
| `mtd2` | `jffs2` | `4,194,304` B (`0x400000`) | `ca69da0835495a4f0b6f76508b4e13d4` | `b3f14711c016c34f45fbdd73cca9bc99753b46ba687983cc8e27abbf236844ab` |

- Bootloader gzip header at `mtd0[0x7D60:0x7D62]` (`1f 8b`): **verified**
- `install_openwrt_lan.py --dry-run` status: **passed** (`The backup checks out: sizes and md5 match, the bootloader is in place.`)

