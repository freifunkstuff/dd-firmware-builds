---
layout: default
title: TP-Link Festa F52-Outdoor v1
---

# TP-Link Festa F52-Outdoor v1

## Freifunk Dresden Firmware

**Version:** `9.1.0-f52-outdoor-v1-r2`

**Downloads:** [Factory-Image](https://github.com/freifunkstuff/dd-firmware-builds/releases/download/ffdd-9.1.0-f52-outdoor-v1-r2/ffdd-9.1.0-f52-outdoor-v1-r2-factory.bin) · [Sysupgrade-Image](https://github.com/freifunkstuff/dd-firmware-builds/releases/download/ffdd-9.1.0-f52-outdoor-v1-r2/ffdd-9.1.0-f52-outdoor-v1-r2-sysupgrade.bin) · [SHA-256-Prüfsummen](https://github.com/freifunkstuff/dd-firmware-builds/releases/download/ffdd-9.1.0-f52-outdoor-v1-r2/SHA256SUMS)

## OpenWrt

OpenWrt SNAPSHOT mit F52-Unterstützung, **LuCI über HTTPS** und Ethernet als **DHCP-Client**. Kein eigener DHCP-Server auf dem LAN; WLAN ist zunächst ausgeschaltet.

**Version:** `openwrt-snapshot-ca6f69be-f52-outdoor-v1-r2`

**Downloads:** [Factory-Image](https://github.com/freifunkstuff/dd-firmware-builds/releases/download/openwrt-snapshot-ca6f69be-f52-outdoor-v1-r2/openwrt-snapshot-ca6f69be-f52-outdoor-v1-r2-factory.bin) · [Sysupgrade-Image](https://github.com/freifunkstuff/dd-firmware-builds/releases/download/openwrt-snapshot-ca6f69be-f52-outdoor-v1-r2/openwrt-snapshot-ca6f69be-f52-outdoor-v1-r2-sysupgrade.bin) · [SHA-256-Prüfsummen](https://github.com/freifunkstuff/dd-firmware-builds/releases/download/openwrt-snapshot-ca6f69be-f52-outdoor-v1-r2/SHA256SUMS)

## Erstinstallation über die Festa-Weboberfläche

1. Passendes **Factory-Image** herunterladen und SHA-256 prüfen.
2. Unter **Management → SSH Server** SSH aktivieren.
3. Per SSH anmelden und die Signaturprüfung ausschalten:

   ```sh
   cliclientd stopcs
   ```

4. Ohne vorherigen Neustart unter **System → Firmware Update** das **F52-Factory-Image** hochladen. Während des Updates die Stromversorgung nicht unterbrechen.
