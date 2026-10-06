#!/usr/bin/env python3
"""Prepare pinned PR-based OpenWrt SNAPSHOT F52 Factory/Sysupgrade build."""

import json
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]


def main() -> None:
    if len(sys.argv) != 2:
        raise ValueError('usage: prepare_openwrt.py CLEAN_PR_CHECKOUT')
    source = Path(sys.argv[1]).resolve()
    lock = json.loads((REPO / 'openwrt-snapshot.json').read_text())
    device = json.loads((REPO / 'openwrt/devices/f52-outdoor-v1.json').read_text())
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if head != lock['commit_sha']:
        raise ValueError('OpenWrt PR head changed; review and update SHA before building')
    if subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True).strip():
        raise ValueError('OpenWrt PR checkout must be clean before preparation')
    profile = (source / 'target/linux/ath79/image/generic-tp-link.mk').read_text()
    block = profile.split(f"define Device/{device['openwrt_device']}\n", 1)[1].split('\nendef', 1)[0]
    if not all(s in block for s in ('TPLINK_BOARD_ID := F52-V1',
                                    'kmod-ath10k-ct ath10k-firmware-qca9888-ct',
                                    'IMAGE_SIZE := 13824k')):
        raise ValueError('PR lacks reviewed F52 image profile or CT firmware')
    dts = (source / 'target/linux/ath79/dts/qca9563_tplink_f52-outdoor-v1.dts').read_text()
    if device['compatible'] not in dts:
        raise ValueError('wrong F52 DTS compatible')
    tool_mk = (source / 'tools/firmware-utils/Makefile').read_text()
    if f"PKG_SOURCE_VERSION:={lock['host_firmware_utils_base_sha']}" not in tool_mk:
        raise ValueError('OpenWrt host safeloader source changed; review PR74 backport')
    tool_patches = source / 'tools/firmware-utils/patches'
    if tool_patches.exists():
        raise ValueError('upstream host patch directory already exists; review F52 support before adding patch')
    tool_patches.mkdir()
    shutil.copyfile(REPO / 'patches/openwrt/100-f52-safeloader-c9da.patch',
                    tool_patches / '100-f52-safeloader-c9da.patch')
    upstream_feeds = (source / 'feeds.conf.default').read_text()
    for name, url in (('luci', 'https://git.openwrt.org/project/luci.git'),
                      ('packages', 'https://git.openwrt.org/feed/packages.git')):
        declaration = f'src-git {name} {url}'
        if upstream_feeds.count(declaration) != 1:
            raise ValueError(f'OpenWrt {name} feed declaration changed; review pinning')
        upstream_feeds = upstream_feeds.replace(
            declaration, declaration + '^' + lock[f'{name}_feed_commit_sha'])
    (source / 'feeds.conf').write_text(upstream_feeds)
    shutil.copytree(REPO / 'openwrt/files', source / 'files', dirs_exist_ok=True)
    config = (REPO / 'openwrt/f52.config').read_text()
    (source / '.config').write_text(config)
    marker = source / 'files/etc/device-build'
    marker.parent.mkdir(parents=True, exist_ok=True)
    label = f"openwrt-snapshot-{head[:8]}-{device['id']}-r{device['revision']}"
    marker.write_text(f'version={label}\nopenwrt_commit={head}\n'
                      f'firmware_utils_pr_commit={lock["firmware_utils_commit_sha"]}\n'
                      f'luci_feed_commit={lock["luci_feed_commit_sha"]}\n'
                      f'packages_feed_commit={lock["packages_feed_commit_sha"]}\n')
    print(label)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, IndexError) as error:
        print(f'OpenWrt preparation failed: {error}', file=sys.stderr)
        raise SystemExit(1)
