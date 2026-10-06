#!/usr/bin/env python3
"""Detect stable OFFICIAL FFDD GitLab tags and propose a reviewed lockfile bump.

Never builds firmware, writes a release, or publishes an image. --write only edits
upstream.json in THIS repository; GitHub Actions then creates a review PR.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
OFFICIAL = 'https://gitlab.freifunk-dresden.de/firmware-developer/firmware.git'
TAG = re.compile(r'^refs/tags/(T_FIRMWARE_((?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)))(\^\{\})?$')


def read_remote_tags(output: str) -> dict[tuple[int, int, int], dict]:
    result: dict[tuple[int, int, int], dict] = {}
    for line in output.splitlines():
        sha, separator, ref = line.partition('\t')
        if not separator or not re.fullmatch('[a-f0-9]{40}', sha):
            continue
        match = TAG.fullmatch(ref)
        if not match:
            continue
        name, version, peeled = match.groups()
        numbers = tuple(map(int, version.split('.')))
        item = result.setdefault(numbers, {'version': version, 'tag': name})
        key = 'commit_sha' if peeled else 'tag_object_sha'
        if key in item and item[key] != sha:
            raise ValueError(f'conflicting GitLab references for {name}')
        item[key] = sha
    # For lightweight tags, the tag ref points directly at the commit.
    for item in result.values():
        if 'tag_object_sha' not in item:
            raise ValueError(f'missing tag object for {item["tag"]}')
        item.setdefault('commit_sha', item['tag_object_sha'])
    return result


def verify_checked_out_tag(source: str, item: dict) -> None:
    with tempfile.TemporaryDirectory(prefix='ffdd-verified-tag-') as d:
        subprocess.run(['git', 'clone', '--quiet', '--depth=1', '--branch', item['tag'], source, d],
                       check=True, stdout=subprocess.DEVNULL)
        object_sha = subprocess.check_output(['git', '-C', d, 'rev-parse', f"refs/tags/{item['tag']}"],
                                             text=True).strip()
        commit = subprocess.check_output(['git', '-C', d, 'rev-parse', 'HEAD'], text=True).strip()
        if (object_sha, commit) != (item['tag_object_sha'], item['commit_sha']):
            raise ValueError(f'GitLab tag {item["tag"]} changed while being verified')
        manifest = (Path(d) / 'build.json').read_text()
        if '"targets"' not in manifest:
            raise ValueError('unexpected FFDD source without build.json targets')


def check_latest(lock: dict, tags: dict) -> dict | None:
    if lock['repository'] != OFFICIAL:
        raise ValueError('upstream repository URL changed; investigate manually')
    current = tuple(map(int, lock['version'].split('.')))
    pinned = tags.get(current)
    if not pinned or any(lock.get(k) != pinned.get(k) for k in ('tag', 'tag_object_sha', 'commit_sha')):
        raise ValueError(f'pinned {lock["version"]} tag moved/disappeared; REFUSE silent update')
    newest = max(tags)
    if newest < current:
        raise ValueError('latest FFDD stable tag is older than pinned version')
    if newest == current:
        return None
    return {'repository': OFFICIAL, **tags[newest]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write', action='store_true', help='write ONLY upstream.json after verification')
    args = parser.parse_args()
    path = REPO / 'upstream.json'
    lock = json.loads(path.read_text())
    output = subprocess.check_output(['git', 'ls-remote', '--tags', OFFICIAL], text=True)
    tags = read_remote_tags(output)
    if not tags:
        raise ValueError('official GitLab returned no stable tags')
    update = check_latest(lock, tags)
    if not update:
        print(f"up to date: {lock['tag']} ({lock['commit_sha']})")
        return
    verify_checked_out_tag(OFFICIAL, update)
    print(f"Review needed: {lock['tag']} -> {update['tag']} ({update['commit_sha']})")
    if args.write:
        path.write_text(json.dumps(update, indent=2) + '\n')
        print('updated upstream.json ONLY; device patches/configs require review and a fresh build')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f'UPSTREAM CHECK ERROR: {error}', file=sys.stderr)
        raise SystemExit(1)
