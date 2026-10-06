#!/usr/bin/env python3
"""Add one experimental device to a CLEAN checkout of a PINNED FFDD release.

Only the temporary checkout is modified. The official repository, base target,
other devices and this repository's vendor patch files are not modified.
"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]


def uncomment_hash_json(text: str) -> dict:
    lines = []
    for line in text.splitlines():
        in_string = escaped = False
        for index, char in enumerate(line):
            if char == '"' and not escaped:
                in_string = not in_string
            if char == '#' and not in_string:
                line = line[:index]
                break
            escaped = char == '\\' and not escaped
        lines.append(line)
    return json.loads('\n'.join(lines))


def check_git(checkout: Path, lock: dict) -> None:
    head = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
    tag = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', f"refs/tags/{lock['tag']}"], text=True).strip()
    if head != lock['commit_sha'] or tag != lock['tag_object_sha']:
        raise ValueError(f'FFDD checkout does not match reviewed {lock["tag"]} commit/tag SHA')
    if subprocess.check_output(['git', '-C', str(checkout), 'status', '--porcelain'], text=True).strip():
        raise ValueError('FFDD checkout is not clean; prepare a fresh release clone')


def device_paths(device: dict, root: Path) -> None:
    ident = device['id']
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,60}', ident):
        raise ValueError(f'invalid device ID: {ident!r}')
    if not re.fullmatch(r'[a-z0-9_.-]+', device['dd_target']):
        raise ValueError('invalid DD build target')
    for key in ('openwrt_device', 'openwrt_platform'):
        if not re.fullmatch(r'[a-z0-9_-]+', device[key]):
            raise ValueError(f'invalid {key}')
    if not isinstance(device['revision'], int) or isinstance(device['revision'], bool) or device['revision'] < 1:
        raise ValueError('device revision must be a positive integer')
    if device.get('patches'):
        patches = (root / device['patches']).resolve()
        if not patches.is_relative_to(root.resolve()) or not patches.is_dir():
            raise ValueError('device patch directory must be within this repository')


def prepare(root: Path, checkout: Path, lock: dict, device: dict) -> str:
    device_paths(device, root)
    check_git(checkout, lock)
    data = uncomment_hash_json((checkout / 'build.json').read_text())
    targets = data['targets']
    base_index, base = next(((i, entry) for i, entry in enumerate(targets)
                             if entry.get('name') == device['dd_target']), (None, None))
    if base is None:
        raise ValueError(f"no FFDD target {device['dd_target']}")
    template = next((item for item in targets if item.get('type') == 'template'
                     and item.get('name') == base['template']), None)
    if template is None:
        raise ValueError('missing FFDD template for selected target')
    cfg = {**template, **base}
    if cfg['openwrt_rev'] != device['expected_openwrt_rev']:
        raise ValueError(f"FFDD {lock['tag']} changed OpenWrt from {device['expected_openwrt_rev']}; review backports")
    for selector in ('selector-patches', 'selector-config', 'selector-files', 'selector-feeds'):
        if cfg[selector] != device['expected_selector']:
            raise ValueError(f'FFDD {selector} changed to {cfg[selector]}; review target configuration')
    target = f"{base['name']}.{device['id']}"
    if any(item.get('name') == target for item in targets):
        raise ValueError(f'target {target} already exists')

    selector = cfg['selector-config']
    original_cfg = checkout / 'fw-configs' / selector / base['config']
    source = original_cfg.read_text()
    pattern = re.compile(r'^(CONFIG_TARGET_DEVICE_[a-z0-9_-]+_DEVICE_[a-z0-9_-]+)=y$', re.M)
    existing = pattern.findall(source)
    if not existing or 'CONFIG_TARGET_PER_DEVICE_ROOTFS=y' not in source:
        raise ValueError('missing FFDD per-device rootfs/selected device profiles')
    source = pattern.sub(lambda match: f'# {match.group(1)} is not set', source)
    symbol = f"CONFIG_TARGET_DEVICE_{device['openwrt_platform']}_DEVICE_{device['openwrt_device']}"
    if re.search(rf'^(# )?{re.escape(symbol)}\b', source, re.M):
        source = re.sub(rf'^# {re.escape(symbol)} is not set$', f'{symbol}=y', source, flags=re.M)
        if f'{symbol}=y' not in source:
            raise ValueError(f'could not enable OpenWrt device {symbol}')
    else:
        source += f'\n{symbol}=y\n'
    package_symbol = symbol.replace('CONFIG_TARGET_DEVICE_', 'CONFIG_TARGET_DEVICE_PACKAGES_', 1)
    if package_symbol not in source:
        source += f'{package_symbol}=""\n'
    if device['rootfs'] == 'squashfs':
        if 'CONFIG_TARGET_ROOTFS_SQUASHFS=y' not in source:
            raise ValueError('DD release does not enable squashfs')
        for key in ('CONFIG_TARGET_ROOTFS_INITRAMFS', 'CONFIG_TARGET_INITRAMFS_FORCE',
                    'CONFIG_TARGET_INITRAMFS_COMPRESSION_NONE'):
            source = source.replace(f'{key}=y', f'# {key} is not set')
    else:
        raise ValueError(f'unsupported filesystem: {device["rootfs"]}')
    if len(re.findall(r'^CONFIG_TARGET_DEVICE_[a-z0-9_-]+_DEVICE_[a-z0-9_-]+=y$', source, re.M)) != 1:
        raise ValueError('device isolation failed; more than one device selected')
    cfg_name = original_cfg.name.removesuffix('.cfg') + f".{device['id']}.cfg"
    (original_cfg.parent / cfg_name).write_text(source)

    patch_selector = f"{cfg['selector-patches']}-{device['id']}"
    patch_dir = checkout / 'fw-patches' / patch_selector
    patch_dir.mkdir()
    base_patches = sorted((checkout / 'fw-patches' / cfg['selector-patches']).glob('*.patch'))
    extra_patches = sorted((root / device['patches']).glob('*.patch')) if device.get('patches') else []
    if not base_patches or (device.get('patches') and not extra_patches):
        raise ValueError('missing DD base or requested device patches')
    names = [p.name for p in base_patches + extra_patches]
    if names != sorted(names) or len(set(names)) != len(names):
        raise ValueError('device patches must follow DD patch order without collisions')
    for patch in base_patches + extra_patches:
        shutil.copy2(patch, patch_dir / patch.name)

    files_selector = f"{cfg['selector-files']}-{device['id']}"
    files_path = checkout / 'fw-files'
    shared = files_path / (files_selector + '.common')
    shared.symlink_to(cfg['selector-files'] + '.common', target_is_directory=True)
    specific = files_path / files_selector
    shutil.copytree(files_path / cfg['selector-files'], specific, symlinks=True)
    release = (specific / 'etc' / 'version').read_text().strip()
    if release != lock['version']:
        raise ValueError(f'FFDD /etc/version={release} differs from reviewed {lock["version"]}')
    # Preserve FFDD's NUMERIC /etc/version: its autoupdater compares integer parts.
    marker = specific / 'etc' / 'dd-device-build'
    marker.write_text(f'ffdd_version={release}\ndevice={device["id"]}\n'
                      f'device_revision=r{device["revision"]}\n'
                      f'display_version={release}-{device["id"]}-r{device["revision"]}\n'
                      f'ffdd_commit={lock["commit_sha"]}\n')

    new_target = {
        'template': base['template'], 'name': target, 'config': cfg_name,
        'openwrt_variant': device['id'], 'selector-patches': patch_selector,
        'selector-files': files_selector, 'disabled': False,
    }
    targets.insert(base_index + 1, new_target)
    (checkout / 'build.json').write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='clean official FFDD tag checkout')
    parser.add_argument('--device', required=True, help='devices/<id>.json')
    args = parser.parse_args()
    root = REPO.resolve()
    lock = json.loads((root / 'upstream.json').read_text())
    device = json.loads((root / 'devices' / (args.device + '.json')).read_text())
    print(prepare(root, args.source.resolve(), lock, device))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'PREPARE ERROR: {error}', file=sys.stderr)
        raise SystemExit(1)
