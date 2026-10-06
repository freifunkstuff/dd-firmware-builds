"""No-network tests for release pinning and DD JSON comment handling."""

import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from prepare import uncomment_hash_json
from update_upstream import OFFICIAL, check_latest, read_remote_tags

TAG_SHA = 'a' * 40
COMMIT_SHA = 'b' * 40


class MetadataTests(unittest.TestCase):
    def test_comments_outside_strings_only(self):
        parsed = uncomment_hash_json('{"url":"https://host/path#fragment", # comment\n "x": 1}')
        self.assertEqual(parsed, {'url': 'https://host/path#fragment', 'x': 1})

    def test_annotated_and_lightweight_tags(self):
        tags = read_remote_tags(f'{TAG_SHA}\trefs/tags/T_FIRMWARE_9.1.0\n'
                                f'{COMMIT_SHA}\trefs/tags/T_FIRMWARE_9.1.0^{{}}\n'
                                f'{COMMIT_SHA}\trefs/tags/T_FIRMWARE_9.2.0\n'
                                f'{TAG_SHA}\trefs/tags/T_FIRMWARE_9.2.0-rc1\n')
        self.assertEqual(tags[(9, 1, 0)]['tag_object_sha'], TAG_SHA)
        self.assertEqual(tags[(9, 1, 0)]['commit_sha'], COMMIT_SHA)
        self.assertEqual(tags[(9, 2, 0)]['commit_sha'], COMMIT_SHA)
        self.assertEqual(len(tags), 2)

    def test_upgrade_requires_review_and_moved_tag_fails(self):
        locked = {'repository': OFFICIAL, 'version': '9.1.0', 'tag': 'T_FIRMWARE_9.1.0',
                  'tag_object_sha': TAG_SHA, 'commit_sha': COMMIT_SHA}
        tags = {(9, 1, 0): dict(locked),
                (9, 2, 0): {'version': '9.2.0', 'tag': 'T_FIRMWARE_9.2.0',
                            'tag_object_sha': 'c' * 40, 'commit_sha': 'd' * 40}}
        self.assertEqual(check_latest(locked, tags)['tag'], 'T_FIRMWARE_9.2.0')
        tags[(9, 1, 0)]['commit_sha'] = 'e' * 40
        with self.assertRaisesRegex(ValueError, 'moved/disappeared'):
            check_latest(locked, tags)


if __name__ == '__main__':
    unittest.main()
