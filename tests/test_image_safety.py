"""Fast offline checks for image consistency and exact build parameters."""

from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verify_images import check_consistent_images, check_embedded_credentials, parse_build_marker


class ImageSafetyTests(unittest.TestCase):
    def test_rootfs_payload_must_match_sysupgrade(self):
        kernel = b'\x7fELF' + b'K' * 120
        squashfs = bytearray(b'hsqs' + b'\x00' * 120)
        struct.pack_into('<Q', squashfs, 40, 110)
        factory_root = bytes(squashfs) + b'\xff' * 24 + b'\xde\xad\xc0\xde'
        sysupgrade = kernel + bytes(squashfs) + b'\xff' * 24 + b'\xff' * 4 + b'FWTOOL'
        self.assertEqual(check_consistent_images(kernel, factory_root, sysupgrade), 110)
        corrupt = bytearray(sysupgrade)
        corrupt[len(kernel) + 60] ^= 1
        with self.assertRaisesRegex(ValueError, 'DIFFERENT SquashFS'):
            check_consistent_images(kernel, factory_root, bytes(corrupt))
        with self.assertRaisesRegex(ValueError, 'DIFFERENT MIPS'):
            check_consistent_images(b'BAD' + kernel, factory_root, sysupgrade)

    def test_unique_nonempty_parameters_must_match_embedded_values(self):
        valid = ("config registration 'registration'\n"
                 "\toption register_service_url 'https://selfsigned.register.freifunk-dresden.de/bot.php?registerkey=abc:def'\n"
                 "config network 'network'\n\toption wifi_mesh_key 'example-mesh-value'\n")
        check_embedded_credentials(valid, 'example-mesh-value', 'abc_def')
        with self.assertRaisesRegex(ValueError, 'mismatched'):
            check_embedded_credentials(valid.replace('registerkey=abc:def', 'registerkey=WRONG'),
                                       'example-mesh-value', 'abc_def')
        with self.assertRaisesRegex(ValueError, 'mismatched'):
            check_embedded_credentials(valid + "option wifi_mesh_key 'OTHER'\n",
                                       'example-mesh-value', 'abc_def')
        with self.assertRaisesRegex(ValueError, 'mismatched'):
            check_embedded_credentials(valid.replace('example-mesh-value', 'DIFFERENT'),
                                       'example-mesh-value', 'abc_def')
        with self.assertRaisesRegex(ValueError, 'missing'):
            check_embedded_credentials(valid, '', '')

    def test_marker_must_include_unique_exact_provenance(self):
        s=('ffdd_version=9.1.0\ndevice=f52-outdoor-v1\ndevice_revision=r1\n'
           'display_version=9.1.0-f52-outdoor-v1-r1\nffdd_commit='+'a'*40+'\n')
        self.assertEqual(parse_build_marker(s)['ffdd_commit'], 'a'*40)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            parse_build_marker(s+'device=f52-outdoor-v1\n')
        with self.assertRaisesRegex(ValueError, 'missing or unexpected'):
            parse_build_marker(s.replace('ffdd_commit='+'a'*40+'\n',''))


if __name__ == '__main__':
    unittest.main()
