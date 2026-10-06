# Freifunk-Dresden-Builds für zusätzliche Geräte

Dieses Repository baut gerätespezifische Varianten der **Freifunk-Dresden-Firmware**. Die offiziellen Quellen werden beim Build aus [Dresdens GitLab](https://gitlab.freifunk-dresden.de/firmware-developer/firmware) geladen; hier liegen nur Geräteprofile, nötige Patches und die GitHub-Actions-Workflows.

**Erstes Gerät:** Festa F52-Outdoor v1. Weitere Geräte können unter [`devices/`](<devices/>) ergänzt werden. Ein manueller [Actions-Build](<.github/workflows/build.yml>) stellt Factory- und Sysupgrade-Images als geprüfte Run-Artefakte bereit. Es wird nichts automatisch auf Router geflasht oder als Firmware-Release veröffentlicht.

Die Versionsbezeichnung kombiniert den Dresdner Release mit einer eigenen Geräte-Revision, zum Beispiel **`9.1.0-f52-outdoor-v1-r2`**. Ein [wöchentlicher Check](<.github/workflows/watch-upstream.yml>) erkennt neue Dresdner Releases und legt einen Review-Branch samt Hinweis an. Nach Prüfung kann daraus die nächste Gerätevariante gebaut werden.
