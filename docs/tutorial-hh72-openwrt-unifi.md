# Tutorial: OpenWrt Installation and UniFi AP Integration on Alcatel LINKHUB HH72VM

A complete guide for flashing OpenWrt, setting up networking, and integrating the **Alcatel LINKHUB HH72VM (`HH72VM-2BALAT3`, board `HH72-V-V2.0`)** with a **UniFi Network Controller** as a wireless access point (Wi-Fi 5, dual-band 2.4 GHz + 5 GHz).

---

## Upstream Credits & Attribution

This project is built upon the invaluable work of the open-source community:

1. **OpenWrt Port for the HH71/HH72 Platform:**
   - Base project: [`sowarden/hh71vm-openwrt`](https://github.com/sowarden/hh71vm-openwrt)
   - Author: **sowarden**
   - Sincere thanks to **sowarden** for maintaining the Linux 4.14 kernel port, Realtek `rtl8192cd`/`rtl8812f` proprietary wireless drivers, the `hh71vm-modemd` modem daemon, and the LuCI interface for the Realtek RTL8197FS SoC.

2. **UniFi Access Point Emulation Daemon:**
   - Base project: [`antoniocosta/unifi-openwrt`](https://github.com/antoniocosta/unifi-openwrt) (`uow`)
   - Author: **Antonio Costa**
   - Thanks to **Antonio Costa** for reverse-engineering and implementing the UniFi L3 Inform protocol and configuration generator.

The adaptations for the **HH72VM** hardware model (MIPS softfloat optimization, Flash overlay sizing, Dropbear SSH adoption support via `syswrapper.sh`, WEXT wireless interface translation, and dynamic DHCP integration with USG/UDM) were developed by **gutmanovaty**:
- GitHub: [https://github.com/gutmanovaty/hh72vm-firmware-openwrt](https://github.com/gutmanovaty/hh72vm-firmware-openwrt)
- GitLab: [https://g.gut.red/gut.red/hh72vm-firmware-openwrt](https://g.gut.red/gut.red/hh72vm-firmware-openwrt)

---

## Hardware Specifications (HH72VM)

- **Model:** Alcatel LINKHUB `HH72VM-2BALAT3` (`HUB72`)
- **Mainboard:** `HH72-V-V2.0`
- **SoC:** Realtek RTL8197FS (MIPS 24Kc @ 500 MHz, softfloat)
- **RAM:** 128 MB DDR2
- **Flash:** 16 MB SPI NOR (`m25p80`)
- **LTE Modem:** Qualcomm Snapdragon X12 (MDM9645), LTE Cat.7 (300/100 Mbps)
- **Ethernet:** 1x Gigabit Ethernet RJ45 (RTL8211F PHY)
- **Wi-Fi 2.4 GHz:** Integrated RTL8197FS (2T2R 802.11b/g/n, driver `rtl8192cd`)
- **Wi-Fi 5 GHz:** Dedicated PCIe module Realtek RTL8812F (2T2R 802.11a/n/ac, up to 866 Mbps)

---

## STEP 1: Backup Stock Flash Memory

Before modifying or flashing any firmware, perform a full 16 MiB SPI NOR flash dump:

1. Connect your PC directly to the router's Ethernet port.
2. Enable Telnet access via the stock Web API by visiting this URL in a browser:
   ```text
   http://192.168.1.1/jrd/webapi?api=SetDeviceMode&params=%7B%22mode%22:1%7D
   ```
3. Connect via Telnet to `192.168.1.1` (username `admin`, password: your web admin password).
4. Launch a local TFTP server on your computer (e.g., `tftpd64` or Python script `scripts/backup_stock_http.py`).
5. Dump and transmit the full flash image:
   ```sh
   dd if=/dev/mtd0 of=/tmp/full_flash_16mb.bin
   tftp -p -l /tmp/full_flash_16mb.bin -r backup_hh72_stock.bin 192.168.1.X
   ```

---

## STEP 2: Flashing OpenWrt

1. Prepare the installation image `openwrt-rtkmipsel-rtl8197f-hh71vm-fwupg.bin`.
2. From the router's Telnet shell, download the image into `/tmp`:
   ```sh
   tftp -g -r openwrt-rtkmipsel-rtl8197f-hh71vm-fwupg.bin -l /tmp/fwupg.bin 192.168.1.X
   ```
3. Write the firmware to flash (`/dev/mtd3` corresponds to `kernel+rootfs`):
   ```sh
   mtd_write write /tmp/fwupg.bin /dev/mtd3
   reboot
   ```
4. After rebooting, the router boots into OpenWrt 19.07-SNAPSHOT.

---

## STEP 3: LAN Configuration (DHCP Client + Rescue Aliases)

By default, OpenWrt boots with static IP `192.168.1.1` and an active DHCP server, which can conflict with an existing gateway (e.g. UniFi USG 3P / UDM).

To integrate the device into an existing LAN without losing connectivity:
1. Log in via SSH: `ssh root@192.168.1.1` (empty password initially).
2. Configure the LAN interface to acquire an IP dynamically via DHCP, disable the local dnsmasq DHCP server, and create static fallback aliases:
   ```sh
   # Disable local DHCP server so it does not interfere with the network
   uci set dhcp.lan.ignore='1'
   uci commit dhcp
   /etc/init.d/dnsmasq restart

   # Configure br-lan as DHCP client
   uci set network.lan.proto='dhcp'
   uci delete network.lan.ipaddr 2>/dev/null
   uci delete network.lan.netmask 2>/dev/null
   uci delete network.lan.gateway 2>/dev/null
   uci delete network.lan.dns 2>/dev/null

   # Add permanent rescue management alias (guarantees access at all times)
   uci set network.lan_mgmt=interface
   uci set network.lan_mgmt.proto='static'
   uci set network.lan_mgmt.ifname='@lan'
   uci set network.lan_mgmt.ipaddr='10.0.3.1'
   uci set network.lan_mgmt.netmask='255.255.255.0'

   # Add secondary fallback alias
   uci set network.lan_fixed=interface
   uci set network.lan_fixed.proto='static'
   uci set network.lan_fixed.ifname='@lan'
   uci set network.lan_fixed.ipaddr='192.168.1.199'
   uci set network.lan_fixed.netmask='255.255.252.0'

   uci commit network
   /etc/init.d/network restart
   ```

---

## STEP 4: Deploying UniFi Daemon (`unifi-openwrt` / `uow`)

The `uow` daemon emulates a UniFi AP (`U7PG2` / UniFi AP-AC-Pro), encrypts Inform protocol payloads (CBC / GCM), and communicates with the UniFi Controller on port 8080.

### 1. Install UniFi Command Emulator (`syswrapper.sh`)
When **Adopt** is clicked in the UniFi Controller, the controller connects via SSH as `ubnt:ubnt` and executes:
```sh
/usr/bin/syswrapper.sh set-adopt <inform_url> <authkey>
```
Install the handler script on the router at `/usr/bin/syswrapper.sh`:
```sh
cat << 'EOF' > /usr/bin/syswrapper.sh
#!/bin/sh
CMD="$1"
shift
STATE_FILE="/etc/unifi-openwrt/state/state.json"

case "$CMD" in
  set-adopt)
    URL="$1"
    KEY="$2"
    logger -t syswrapper "set-adopt called: URL=$URL KEY=$KEY"
    if [ -f "$STATE_FILE" ] && [ -n "$KEY" ]; then
      sed -i -e "s/\"key\": *\"[^\"]*\"/\"key\": \"$KEY\"/" \
             -e "s/\"adopted\": *false/\"adopted\": true/" \
             -e "s|\"inform_url\": *\"[^\"]*\"|\"inform_url\": \"$URL\"|" "$STATE_FILE"
      killall -HUP uow 2>/dev/null || /etc/init.d/unifi-openwrt restart
    fi
    exit 0
    ;;
  set-inform)
    URL="$1"
    logger -t syswrapper "set-inform called: URL=$URL"
    if [ -f "$STATE_FILE" ] && [ -n "$URL" ]; then
      sed -i "s|\"inform_url\": *\"[^\"]*\"|\"inform_url\": \"$URL\"|" "$STATE_FILE"
      killall -HUP uow 2>/dev/null || /etc/init.d/unifi-openwrt restart
    fi
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
EOF
chmod 755 /usr/bin/syswrapper.sh
```

### 2. Configure `ubnt` User for the Controller
Create the system account used by UniFi Network during adoption:
```sh
grep -q '^ubnt:' /etc/passwd || echo 'ubnt:x:0:0:ubnt:/root:/bin/ash' >> /etc/passwd
printf 'ubnt\nubnt\n' | passwd ubnt
```

### 3. Service Installation and Startup
Deploy the optimized MIPS binary `uow-mipsel.gz` into `/etc/unifi-openwrt/uow.gz` and set up the init service (or use the automated deployment script `python scripts/deploy_uow.py --host <ROUTER_IP>`):

Enable and start the service:
```sh
/etc/init.d/unifi-openwrt enable
/etc/init.d/unifi-openwrt start
```

---

## STEP 5: UniFi Controller Adoption

1. Open your **UniFi Network** dashboard in a browser (`https://<CONTROLLER_IP>`).
2. Under **UniFi Devices**, the new device `AC Pro` will appear with the status **Pending Adoption** / **Click to Adopt**.
3. Click **Adopt**.
4. The controller connects via SSH, supplies its encryption key (`authkey`), and switches the device state to **Online / Adopted** with **AES-GCM** encryption.

---

## STEP 6: Wi-Fi Integration

To broadcast your UniFi WLAN networks:
1. Disable the stock default SSIDs:
   ```sh
   uci set wireless.default_radio0.disabled='1'
   uci set wireless.default_radio1.disabled='1'
   ```
2. Configure your unified UniFi wireless credentials:
   ```sh
   # 2.4 GHz Band (radio0):
   uci set wireless.default_radio0.ssid='YourNetwork 2.4G'
   uci set wireless.default_radio0.encryption='psk2+ccmp'
   uci set wireless.default_radio0.key='YourWiFiPassword'
   uci set wireless.default_radio0.disabled='0'

   # 5 GHz Band (radio1):
   uci set wireless.default_radio1.ssid='YourNetwork 5G'
   uci set wireless.default_radio1.encryption='psk2+ccmp'
   uci set wireless.default_radio1.key='YourWiFiPassword'
   uci set wireless.default_radio1.disabled='0'

   uci commit wireless
   wifi reload
   ```

The Alcatel LINKHUB HH72VM now operates as a full-fledged UniFi Access Point, serving connected clients directly onto your local network.
