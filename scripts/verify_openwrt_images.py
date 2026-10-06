#!/usr/bin/env python3
"""Check PR-based OpenWrt F52 Factory/Sysupgrade without booting or flashing."""

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

from verify_images import check_consistent_images, parse_partitions

REPO = Path(__file__).resolve().parents[1]


def run(*args: str) -> str:
    return subprocess.check_output(args, text=True, stderr=subprocess.PIPE)


def check_mips_elf32(kernel: bytes) -> int:
    """Validate loader address and PT_LOADs, not merely the ELF magic."""
    if len(kernel) < 84 or kernel[:6] != b'\x7fELF\x01\x02':
        raise ValueError('kernel is not ELF32 big-endian')
    (elf_type, machine, version, entry, phoff, _shoff, _flags, _ehsize,
     phentsize, phnum, *_rest) = struct.unpack_from('>HHIIIIIHHHHHH', kernel, 16)
    if elf_type != 2 or machine != 8 or version != 1 or phentsize != 32 or not 1 <= phnum <= 16:
        raise ValueError('kernel ELF header is not executable MIPS with valid program headers')
    if phoff + phnum * phentsize > len(kernel):
        raise ValueError('kernel ELF program headers extend beyond image')
    entry_covered = False
    for index in range(phnum):
        kind, offset, _vaddr, paddr, filesz, memsz, _flags, _align = struct.unpack_from(
            '>IIIIIIII', kernel, phoff + index * phentsize)
        if kind != 1:
            continue
        if (offset + filesz > len(kernel) or memsz < filesz or
                not 0x80000000 <= paddr < paddr + memsz <= 0x88000000):
            raise ValueError('kernel ELF PT_LOAD outside F52 128-MiB RAM or input file')
        entry_covered |= paddr <= entry < paddr + memsz
    if not entry_covered:
        raise ValueError('ELF entry not covered by a valid RAM PT_LOAD')
    return entry


def verify(source: Path, out: Path) -> dict:
    lock = json.loads((REPO / 'openwrt-snapshot.json').read_text())
    device = json.loads((REPO / 'openwrt/devices/f52-outdoor-v1.json').read_text())
    if out.exists() and list(out.iterdir()):
        raise ValueError('output directory must be empty')
    if run('git', '-C', str(source), 'rev-parse', 'HEAD').strip() != lock['commit_sha']:
        raise ValueError('OpenWrt PR source revision does not match reviewed SHA')
    platform = 'ath79/generic'
    images = source / 'bin/targets' / platform
    prefix = f"*{device['openwrt_device']}-squashfs-"
    def only(kind: str) -> Path:
        files = list(images.glob(prefix + kind + '.bin'))
        if len(files) != 1:
            raise ValueError(f'expected exactly one {kind} F52 image, found {files}')
        return files[0]
    factory, upgrade = only('factory'), only('sysupgrade')
    if list(images.glob('*f52-outdoor-v1*initramfs*')):
        raise ValueError('unexpected RAM-only image in persistent factory build')
    host = source / 'staging_dir/host/bin'
    safeloader, fwtool = host / 'tplink-safeloader', host / 'fwtool'
    info = run(str(safeloader), '-i', str(factory))
    try:
        support = info.split('[Support list]', 1)[1].split('[Partition table]', 1)[0].strip().splitlines()
    except IndexError:
        raise ValueError('factory lacks complete SupportList metadata') from None
    if support != ['SupportList:', device['factory_support_list']]:
        raise ValueError('factory SupportList is not exclusively Festa F52')
    if not re.search(rf'^Compatibility level: {device["factory_compat_level"]}$', info, re.M):
        raise ValueError('factory firmware compatibility level differs')
    payload = parse_partitions(info, 'Firmware image partitions:')
    layout = parse_partitions(info, '[Partition table]')
    if set(payload) != {'partition-table', 'soft-version', 'support-list', 'os-image', 'file-system'}:
        raise ValueError('unexpected factory payload partitions')
    start, end = device['firmware_start'], device['firmware_end']
    kernel_base, kernel_space = layout['os-image']
    root_base, root_space = layout['file-system']
    if not (kernel_base == start < kernel_base + payload['os-image'][1] <= root_base
            and root_base + payload['file-system'][1] <= root_base + root_space <= end):
        raise ValueError('factory kernel/filesystem do not fit protected F52 firmware region')
    protected = {
        'fs-uboot': (0x000000, 0x020000),
        'partition-table': (0x020000, 0x002000),
        'default-mac': (0x030000, 0x001000),
        'support-list': (0x031000, 0x000100),
        'product-info': (0x031100, 0x000400),
        'soft-version': (0x032000, 0x000100),
        'user-config': (0xdc0000, 0x030000),
        'mutil-log': (0xf30000, 0x080000),
        'oops': (0xfb0000, 0x040000),
        'radio': (0xff0000, 0x010000),
    }
    if set(layout) != set(protected) | {'os-image', 'file-system'}:
        raise ValueError('factory changed F52 vendor partition names')
    if any(layout[name] != address for name, address in protected.items()):
        raise ValueError('factory changed protected bootloader, identity, config, log or ART regions')
    if not (root_base % 0x10000 == 0 and kernel_base + kernel_space <= root_base and
            root_base + root_space <= end):
        raise ValueError('factory kernel/rootfs alignment or reserved partition bounds differ')

    with tempfile.TemporaryDirectory(prefix='openwrt-f52-image-check-') as d:
        temp = Path(d)
        run(str(safeloader), '-x', str(factory), '-d', d)
        kernel = (temp / 'os-image').read_bytes()
        rootfs = (temp / 'file-system').read_bytes()
        entry_point = check_mips_elf32(kernel)
        if rootfs[:4] != b'hsqs':
            raise ValueError('factory does not contain SquashFS')
        used = check_consistent_images(kernel, rootfs, upgrade.read_bytes())
        header = next((kernel.find(x, 0, 65536) for x in
                       (b'\x6d\x00\x00\x80\x00', b'\x5d\x00\x00\x80\x00')
                       if kernel.find(x, 0, 65536) > 0), None)
        if header is None:
            raise ValueError('missing ath79 LZMA kernel in ELF payload')
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        plain = decoder.decompress(kernel[header:])
        if not decoder.eof or device['compatible'].encode() not in plain:
            raise ValueError('kernel lacks F52 device-tree compatible')
        if entry_point + len(plain) >= 0x81800000:
            raise ValueError('unpacked factory kernel overlaps default ath79 LZMA loader at 0x81800000')
        root = temp / 'file-system'
        names = [s.removeprefix('squashfs-root/') for s in run('unsquashfs', '-ls', str(root)).splitlines()]
        for required in device['required_rootfs_paths']:
            if not any(fnmatch.fnmatchcase(name, required) for name in names):
                raise ValueError(f'F52 radio component not in actual rootfs: {required}')
        release = run('unsquashfs', '-cat', str(root), 'etc/openwrt_release')
        if not re.search(r"^DISTRIB_RELEASE='SNAPSHOT'$", release, re.M):
            raise ValueError('not labelled OpenWrt SNAPSHOT in /etc/openwrt_release')
        rev = re.search(r"^DISTRIB_REVISION='([^']+)'$", release, re.M)
        if not rev:
            raise ValueError('missing OpenWrt revision')
        marker = run('unsquashfs', '-cat', str(root), 'etc/device-build')
        expected_label = f"openwrt-snapshot-{lock['commit_sha'][:8]}-{device['id']}-r{device['revision']}"
        expected_marker = {f'version={expected_label}', f'openwrt_commit={lock["commit_sha"]}',
                           f'firmware_utils_pr_commit={lock["firmware_utils_commit_sha"]}'}
        if set(marker.splitlines()) != expected_marker or len(marker.splitlines()) != 3:
            raise ValueError('image build revision or pinned PR provenance marker differs')
        metadata = temp / 'upgrade.json'
        run(str(fwtool), '-i', str(metadata), str(upgrade))
        upgrade_info = json.loads(metadata.read_text())
        if upgrade_info.get('supported_devices') != [device['compatible']]:
            raise ValueError('OpenWrt sysupgrade advertises wrong model')

    profiles = json.loads((images / 'profiles.json').read_text())
    p = profiles.get('profiles', {}).get(device['openwrt_device'])
    if not p or device['compatible'] not in p.get('supported_devices', []):
        raise ValueError('F52 image profile/supported_devices absent')
    required = {'kmod-ath10k-ct', 'ath10k-firmware-qca9888-ct'}
    if not required.issubset(set(p.get('device_packages', []))):
        raise ValueError('OpenWrt F52 DevicePackages do not include CT/QCA9888 firmware')
    by_type = {row['type']: row for row in p.get('images', [])}
    if set(by_type) != {'factory', 'sysupgrade'}:
        raise ValueError('unexpected F52 image types in profiles.json')
    for kind, file in (('factory', factory), ('sysupgrade', upgrade)):
        if by_type[kind]['sha256'] != hashlib.sha256(file.read_bytes()).hexdigest():
            raise ValueError(f'profiles.json {kind} hash does not match actual image')

    out.mkdir(parents=True, exist_ok=True)
    label = f"openwrt-snapshot-{lock['commit_sha'][:8]}-{device['id']}-r{device['revision']}"
    files = {}
    for kind, source_image in (('factory', factory), ('sysupgrade', upgrade)):
        dest = out / f'{label}-{kind}.bin'
        shutil.copyfile(source_image, dest)
        files[kind] = {'name': dest.name, 'bytes': dest.stat().st_size,
                       'sha256': hashlib.sha256(dest.read_bytes()).hexdigest()}
    report = {'label': label, 'status': 'UNTESTED-NO-FLASH', 'base': 'OpenWrt SNAPSHOT',
              'openwrt_revision': rev.group(1), 'openwrt_commit': lock['commit_sha'],
              'openwrt_pr': lock['pull_request'], 'firmware_utils_pr': lock['firmware_utils_pull_request'],
              'firmware_utils_commit': lock['firmware_utils_commit_sha'],
              'device_revision': device['revision'], 'factory_support_list': device['factory_support_list'],
              'squashfs_used_bytes': used, 'firmware_region_start': start, 'firmware_region_end': end,
              'files': files}
    (out / 'build-summary.json').write_text(json.dumps(report, indent=2) + '\n')
    (out / 'SHA256SUMS').write_text(''.join(f'{x["sha256"]}  {x["name"]}\n' for x in files.values()))
    return report


if __name__ == '__main__':
    try:
        if len(sys.argv) != 3:
            raise ValueError('usage: verify_openwrt_images.py OPENWRT_SOURCE OUTPUT_DIR')
        print(json.dumps(verify(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()), indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f'OpenWrt F52 image verification failed: {error}', file=sys.stderr)
        raise SystemExit(1)
