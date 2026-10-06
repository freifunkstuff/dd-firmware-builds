# Freifunk-Dresden-Builds für zusätzliche Geräte

Dieses Repository baut gerätespezifische Varianten der **Freifunk-Dresden-Firmware** sowie experimentelle **OpenWrt-SNAPSHOT-Images**. Die Quellstände werden beim Build aus den jeweiligen Upstream-Repositories geladen; hier liegen nur Geräteprofile, nötige Patches und GitHub-Actions-Workflows.

**Erstes Gerät:** Festa F52-Outdoor v1. Weitere Geräte können unter [`devices/`](<devices/>) ergänzt werden. Manuelle Actions-Builds für [Dresden](<.github/workflows/build.yml>) und [OpenWrt](<.github/workflows/build-openwrt.yml>) stellen Factory- und Sysupgrade-Images als geprüfte Run-Artefakte bereit. Es wird nichts automatisch geflasht oder als Release veröffentlicht.

Die Versionsbezeichnung trennt Upstream und unsere Geräte-Revision: **`9.1.0-f52-outdoor-v1-r2`** (Dresden) oder **`openwrt-snapshot-ca6f69be-f52-outdoor-v1-r1`** (OpenWrt-PR-Commit). Ein [wöchentlicher Check](<.github/workflows/watch-upstream.yml>) meldet neue Dresdner Releases zur Prüfung.
