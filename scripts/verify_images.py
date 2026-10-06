#!/usr/bin/env python3
"""Fail-closed OFFLINE checks for an experimental single-device FFDD build.

This program reads factory/sysupgrade files and unpacks them in a temporary
folder; it never uploads, boots, writes flash or proves physical bootability.
"""

import argparse
import fnmatch
import hashlib
import json
import lzma
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]


def run(*argv: str) -> str:
    return subprocess.check_output(argv, text=True, stderr=subprocess.PIPE)


def parse_partitions(text: str, title: str) -> dict[str, tuple[int, int]]:
    if title not in text:
        raise ValueError(f'missing safeloader section: {title}')
    section = text.split(title, 1)[1].split('\n[', 1)[0]
    result = {}
    for line in section.splitlines():
        match = re.fullmatch(r'([a-fA-F0-9]{8})\s+([a-fA-F0-9]{8})\s+(\S+)', line.strip())
        if match:
            result[match[3]] = (int(match[1], 16), int(match[2], 16))
    if not result:
        raise ValueError(f'no partitions parsed from safeloader section {title}')
    return result


def parse_build_marker(text: str) -> dict[str, str]:
    """A lab artifact's provenance must be unambiguous and COMPLETE."""
    result = {}
    for line in text.splitlines():
        key, sep, value = line.partition('=')
        if not sep or not re.fullmatch(r'[a-z_]+', key) or key in result:
            raise ValueError('invalid or duplicate /etc/dd-device-build key')
        result[key] = value
    expected_keys = {'ffdd_version', 'device', 'device_revision', 'display_version', 'ffdd_commit'}
    if set(result) != expected_keys:
        raise ValueError('missing or unexpected /etc/dd-device-build keys')
    return result


def check_public_credentials(text: str) -> None:
    """Check exact, unique UCI values; substring matching would leak keys."""
    mesh = re.findall(r"^\s*option\s+wifi_mesh_key\s+'([^']*)'\s*$", text, re.M)
    registration = re.findall(r"^\s*option\s+register_service_url\s+'([^']*)'\s*$", text, re.M)
    expected_url = 'https://selfsigned.register.freifunk-dresden.de/bot.php?registerkey='
    if mesh != ['custom-firmware-key'] or registration != [expected_url]:
        raise ValueError('unreviewed, duplicate or real DD credentials: REFUSE public artifact upload')


def check_consistent_images(kernel: bytes, factory_root: bytes, upgrade: bytes) -> int:
    """Check both flashable outputs carry byte-identical SquashFS data."""
    if len(factory_root) < 100 or factory_root[:4] != b'hsqs':
        raise ValueError('factory image lacks valid SquashFS magic/superblock')
    if factory_root[-4:] != b'\xde\xad\xc0\xde':
        raise ValueError('missing factory-only JFFS2 EOF marker')
    squashfs_used = struct.unpack_from('<Q', factory_root, 40)[0]
    if not 96 <= squashfs_used <= len(factory_root) - 4:
        raise ValueError('invalid SquashFS bytes_used in factory payload')
    if upgrade[:len(kernel)] != kernel:
        raise ValueError('factory and sysupgrade contain DIFFERENT MIPS kernels')
    upgrade_root = upgrade[len(kernel):]
    if len(upgrade_root) < squashfs_used or upgrade_root[:4] != b'hsqs':
        raise ValueError('sysupgrade contains no valid SquashFS at the expected position')
    if upgrade_root[:squashfs_used] != factory_root[:squashfs_used]:
        raise ValueError('factory and sysupgrade contain DIFFERENT SquashFS data or credentials')
    return squashfs_used


def get_release_file(root: Path, device: dict, kind: str) -> Path:
    entries = list(root.glob(f'*{device["openwrt_device"]}-squashfs-{kind}.bin'))
    if len(entries) != 1 or not entries[0].is_file():
        raise ValueError(f'expected exactly one F52 {kind} image under {root}; found {entries}')
    return entries[0]


def verify(source: Path, device: dict, lock: dict, out: Path) -> dict:
    if out.exists() and list(out.iterdir()):
        raise ValueError(f'output destination must be empty: {out}')
    if device.get('image_format') != 'tplink-safeloader':
        raise ValueError('no reviewed verifier for this device image format; add one before publishing')
    target = f"{device['dd_target']}.{device['id']}"
    root = source / 'workdir' / '_output' / target / 'images'
    factory = get_release_file(root, device, 'factory')
    upgrade = get_release_file(root, device, 'sysupgrade')
    if list(root.glob('*initramfs*')):
        raise ValueError('unexpected RAM-only image: FFDD boot requires persistent flash/overlay')
    buildroot = source / 'workdir' / (device['expected_openwrt_rev'][:9] + '.' + device['id'])
    safeloader = buildroot / 'staging_dir/host/bin/tplink-safeloader'
    fwtool = buildroot / 'staging_dir/host/bin/fwtool'
    if not safeloader.is_file() or not fwtool.is_file():
        raise ValueError('missing patched OpenWrt host tools in FFDD buildroot')

    text = run(str(safeloader), '-i', str(factory))  # factory ONLY; -i on sysupgrade crashes old tool
    if text.count(device['factory_support_list']) != 1:
        raise ValueError('factory SupportList mismatch (wrong vendor/model or multiple entries)')
    if not re.search(rf'^Compatibility level: {device["factory_compat_level"]}$', text, re.M):
        raise ValueError('factory software compatibility level does not match device')
    contents = parse_partitions(text, 'Firmware image partitions:')
    declared = parse_partitions(text, '[Partition table]')
    expected_sections = {'partition-table', 'soft-version', 'support-list', 'os-image', 'file-system'}
    if set(contents) != expected_sections:
        raise ValueError(f'unexpected factory payload sections: {contents.keys()}')
    firmware_start, firmware_end = device['firmware_start'], device['firmware_end']
    k_start, k_space = declared['os-image']
    r_start, r_space = declared['file-system']
    if not (firmware_start == k_start < k_start + contents['os-image'][1] <= r_start
            and r_start + contents['file-system'][1] <= r_start + r_space <= firmware_end):
        raise ValueError('factory kernel/rootfs payloads overflow firmware partition or overlap')
    if 'radio' not in declared or declared['radio'][0] < firmware_end:
        raise ValueError('calibration partition boundary missing')
    if 'fs-uboot' not in declared or declared['fs-uboot'][0] != 0:
        raise ValueError('bootloader partition boundary missing')

    with tempfile.TemporaryDirectory(prefix='ffdd-firmware-verify-') as directory:
        temp = Path(directory)
        run(str(safeloader), '-x', str(factory), '-d', directory)
        kernel = (temp / 'os-image').read_bytes()
        rootfs = temp / 'file-system'
        if kernel[:4] != b'\x7fELF' or rootfs.open('rb').read(4) != b'hsqs':
            raise ValueError('factory does not carry MIPS ELF kernel plus squashfs filesystem')
        if not any(kernel.find(header, 0, 65536) > 0 for header in
                   (b'\x6d\x00\x00\x80\x00', b'\x5d\x00\x00\x80\x00')):
            raise ValueError('no expected compressed ath79 ELF kernel')
        locs = [kernel.find(header, 0, 65536) for header in
                (b'\x6d\x00\x00\x80\x00', b'\x5d\x00\x00\x80\x00')]
        first = min(offset for offset in locs if offset > 0)
        decompressor = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        plain = decompressor.decompress(kernel[first:])
        if not decompressor.eof or device['compatible'].encode() not in plain:
            raise ValueError('wrong device tree compatible within decompressed kernel')
        if rootfs.stat().st_size != contents['file-system'][1]:
            raise ValueError('extracted filesystem differs from factory payload length')
        factory_root = rootfs.read_bytes()
        # Safeloader sysupgrade is kernel || squashfs || padding || fwtool metadata.
        # Factory has different framing plus a factory-only DEADC0DE marker.
        squashfs_used = check_consistent_images(kernel, factory_root, upgrade.read_bytes())
        listings = run('unsquashfs', '-ls', str(rootfs)).splitlines()
        names = [item.removeprefix('squashfs-root/') for item in listings]
        for required in device['required_rootfs_paths']:
            if not any(fnmatch.fnmatchcase(name, required) for name in names):
                raise ValueError(f'missing DD radio/mesh component: {required}')
        version = run('unsquashfs', '-cat', str(rootfs), 'etc/version').strip()
        marker = run('unsquashfs', '-cat', str(rootfs), 'etc/dd-device-build')
        credentials = run('unsquashfs', '-cat', str(rootfs), 'etc/config/credentials')
        expected_label = f"{lock['version']}-{device['id']}-r{device['revision']}"
        expected_marker = {
            'ffdd_version': lock['version'],
            'device': device['id'],
            'device_revision': f"r{device['revision']}",
            'display_version': expected_label,
            'ffdd_commit': lock['commit_sha'],
        }
        if version != lock['version'] or parse_build_marker(marker) != expected_marker:
            raise ValueError('DD version or device ID/revision/source commit in rootfs differs from reviewed lock')
        check_public_credentials(credentials)
        metadata = temp / 'upgrade.json'
        run(str(fwtool), '-i', str(metadata), str(upgrade))
        info = json.loads(metadata.read_text())
        if info.get('supported_devices') != [device['compatible']]:
            raise ValueError(f'wrong sysupgrade supported device: {info.get("supported_devices")}')

    out.mkdir(parents=True, exist_ok=True)
    label = f"ffdd-{lock['version']}-{device['id']}-r{device['revision']}"
    files = {}
    for kind, original in [('factory', factory), ('sysupgrade', upgrade)]:
        destination = out / f'{label}-{kind}.bin'
        shutil.copyfile(original, destination)
        files[kind] = {
            'filename': destination.name, 'source_name': original.name,
            'bytes': destination.stat().st_size,
            'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
        }
    report = {
        'label': label, 'status': 'UNTESTED-LAB-ONLY', 'official_dd_release': lock['version'],
        'device_revision': device['revision'], 'device': device['id'],
        'dd_tag': lock['tag'], 'dd_tag_object_sha': lock['tag_object_sha'],
        'dd_commit': lock['commit_sha'],
        'config': 'public CI placeholders; not registered with Dresden network',
        'factory_support_list': device['factory_support_list'],
        'factory_compat_level': device['factory_compat_level'],
        'firmware_partition': {'start': firmware_start, 'end': firmware_end},
        'factory_payload': {
            'kernel_base': k_start, 'kernel_bytes': contents['os-image'][1],
            'filesystem_base': r_start, 'filesystem_bytes': contents['file-system'][1],
            'squashfs_used_bytes': squashfs_used,
            'available_bytes_after_rootfs': firmware_end - r_start - contents['file-system'][1],
        },
        'files': files,
    }
    (out / 'build-summary.json').write_text(json.dumps(report, indent=2) + '\n')
    (out / 'SHA256SUMS').write_text(''.join(f'{item["sha256"]}  {item["filename"]}\n'
                                            for item in files.values()))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--device', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads((REPO / 'upstream.json').read_text())
    device = json.loads((REPO / 'devices' / (args.device + '.json')).read_text())
    print(json.dumps(verify(args.source.resolve(), device, lock, args.out.resolve()), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f'IMAGE CHECK ERROR: {error}', file=sys.stderr)
        raise SystemExit(1)
