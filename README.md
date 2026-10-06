# Experimental Freifunk Dresden device builds

**Not an official Freifunk Dresden release. No image in this repository has been boot-tested or flashed on a F52.** [Freifunk Dresden](https://gitlab.freifunk-dresden.de/firmware-developer/firmware) remains the source of its firmware, files and `ddmesh` feed. This small repository adds only independently versioned device definitions, temporary source patches, CI checks and release tracking. Initially: Festa F52-Outdoor v1.

## What is pinned, and what gets built

- [`upstream.json`](<upstream.json>) locks the official GitLab `T_FIRMWARE_9.1.0` **annotated tag object and peeled commit**, not the lagging GitHub mirror. FFDD 9.1.0 uses OpenWrt v25.12.4 for ath79.
- [`devices/f52-outdoor-v1.json`](<devices/f52-outdoor-v1.json>) selects the one OpenWrt F52 profile and independent device revision **r1**. Two [device patches](<patches/f52/>) backport the OpenWrt F52 PR and `F52-V1` host safeloader entry to the pinned OpenWrt release. When both changes arrive in the FFDD OpenWrt base, remove these backports after review.
- [`scripts/prepare.py`](<scripts/prepare.py>) works only on a **clean checkout** of the reviewed GitLab tag. It generates a *temporary* FFDD target by deriving that release's config, copying its release patches and adding this device's patches. It does not vendor or change FFDD source here. The original target stays unchanged. It adds `/etc/dd-device-build` inside this device's image, identifying `9.1.0-f52-outdoor-v1-r1` and the FFDD source SHA.
- Crucially, FFDD's **numeric `/etc/version` stays `9.1.0`**: its updater compares three integer components. The device-specific revision is only in `/etc/dd-device-build`, artifact names and metadata. Increment r1→r2 for device-local changes; an upstream FFDD 9.2.0 update yields `9.2.0-f52-outdoor-v1-r2` without changing the meaning of either number.
- Dresden's normal `build.sh` then fetches OpenWrt, packages/routing feeds and source archives and builds **persistent Factory + Sysupgrade**, not Initramfs (DD's multi-reboot first boot needs writable overlay). [`scripts/verify_images.py`](<scripts/verify_images.py>) checks the *actual* F52 factory payload, support-list, flash bounds, compressed F52 DTB, 5-GHz firmware, BMXD and sysupgrade metadata. Images are copied to separately named, SHA-256-labelled artifacts.

## GitHub Actions

1. Run **Build experimental DD device firmware** → **Run workflow** → `device=all` (currently one device) or `f52-outdoor-v1`. The [`build` workflow](<.github/workflows/build.yml>) has read-only GitHub permissions, downloads FFDD from official GitLab, rejects unexpected tag/commit or production mesh credentials, and uploads **UNTESTED** run artifacts only after validation. It does **not** publish a GitHub Release or touch a router.
2. Hosted `ubuntu-24.04` runners are reported with 4 vCPU/16 GiB RAM/**14 GiB SSD**. The proven local F52 single-device build took about **53 min** of `make` and occupied **about 11 GiB** in FFDD `workdir`+`dl`; runners may start with less free space. The job removes expendable hosted software and **fails early under 20 GiB free** rather than risking the runner's disk. If that never fits, assign a self-hosted/larger Actions runner with **≥25–30 GiB free** and set the repository variable `FFDD_RUNNER` to its runner label. Nothing in the build requires a personal GitHub PAT. First build downloads FFDD sources and packages, so network access is expected.
3. **Suggest reviewed FFDD release updates** ([workflow](<.github/workflows/watch-upstream.yml>)) runs weekly or manually. [`scripts/update_upstream.py`](<scripts/update_upstream.py>) checks **official GitLab stable tags**, verifies object SHA + peeled commit and rejects moved tags. It pushes a **PR-ready branch changing only `upstream.json`** and opens a GitHub Issue with a compare/PR link. The **freifunkstuff organization currently forbids Actions-created Pull Requests** (repository-level attempt got `Conflict`); a human opens the PR via that link. No org-wide setting is changed, no firmware is auto-published. GitHub can disable scheduled workflows on an inactive public repo; the manual trigger remains.
4. An FFDD-update branch or PR is intentionally **not a green light to ship**: inspect its new OpenWrt revision, source/patch applicability, DD runtime API and devices; update device manifests/patches as needed, then manually run the build against the reviewed branch and inspect images.

## Local preparation (no firmware flashing)

```sh
git clone --depth=1 --branch T_FIRMWARE_9.1.0 \
  https://gitlab.freifunk-dresden.de/firmware-developer/firmware.git source
python3 scripts/prepare.py --source source --device f52-outdoor-v1
(cd source && ./build.sh devices ath79.25.generic.f52-outdoor-v1)
# Full DD build needs ample disk, dependencies and time:
(cd source && ./build.sh ath79.25.generic.f52-outdoor-v1 -- -j2 V=s)
python3 scripts/verify_images.py --source source --device f52-outdoor-v1 --out dist/f52-outdoor-v1
```

`build.sh` itself applies OpenWrt patches **only when creating a fresh buildroot** and may silently ignore some patch/feed errors; the isolated target name, specific validation and extracted actual filesystem are intentional. The original F52 single-device build that established these checks is documented separately in the local F52 research workspace, **not** a release produced by this GitHub CI.

## Security and deployment boundaries

Public CI passes **no** `FF_MESH_KEY` or `FF_REGISTERKEY_PREFIX`: its source images have `custom-firmware-key` and an empty registration token. They are **hardware/first-boot test artifacts, not proven production FFDD nodes**. Do not enter community secrets into public GitHub Actions secrets for this workflow: any firmware containing them is an extractable public artifact; obtain an authorized provisioning/release process from the community before actual deployment. Never paste keys, private flash dumps or per-device calibration into issues/logs.

The F52 factory file uses a **Festa** model SupportList. A potentially installed **Omada OEM** web updater is a separate untested compatibility problem; sysupgrade is only for an already running compatible OpenWrt. Neither U-Boot SPI-NOR restoration nor the FFDD kernel/boot sequence has been tested physically here. Before any later, separately authorized installation: confirm the current OEM firmware, preserve the private stock flash backup, isolate the AP from the production LAN and watch its expected multi-reboot first boot via serial/Ethernet.

## Adding another device

Add one `devices/<id>.json` with the target/subtarget profile, independently incremented revision and a reviewed image verifier strategy. Device patches can be omitted when hardware support and vendor image tooling are already in OpenWrt. The build matrix picks up new JSON files automatically. A new image format **must** get explicit offline verification before uploading artifacts; the current verified strategy is TP-Link safeloader Factory+Sysupgrade only.
