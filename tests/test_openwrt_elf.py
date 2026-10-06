"""No-network unit tests for F52 MIPS ELF boot geometry."""

from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verify_openwrt_images import check_ap_network, check_mips_elf32


def fake_elf() -> bytearray:
    data = bytearray(0x1000 + 1024)
    data[:52] = struct.pack('>16sHHIIIIIHHHHHH', b'\x7fELF\x01\x02\x01' + b'\x00' * 9,
                            2, 8, 1, 0x80060000, 52, 0, 0, 52, 32, 1, 0, 0, 0)
    data[52:84] = struct.pack('>IIIIIIII', 1, 0x1000, 0x80060000,
                               0x80060000, 1024, 1024, 5, 0x1000)
    return data


class ElfTests(unittest.TestCase):
    def test_entry_and_segments_in_f52_ram(self):
        self.assertEqual(check_mips_elf32(fake_elf()), 0x80060000)

    def test_wrong_cpu_and_out_of_ram_load_rejected(self):
        wrong_cpu = fake_elf()
        wrong_cpu[18:20] = struct.pack('>H', 3)
        with self.assertRaisesRegex(ValueError, 'MIPS'):
            check_mips_elf32(wrong_cpu)
        wrong_addr = fake_elf()
        wrong_addr[52 + 12:52 + 16] = struct.pack('>I', 0x89000000)
        with self.assertRaisesRegex(ValueError, 'outside F52'):
            check_mips_elf32(wrong_addr)

    def test_first_boot_never_serves_lan_dhcp_or_ra(self):
        root = Path(__file__).resolve().parents[1] / 'openwrt/files/etc'
        network = (root / 'config/network').read_text()
        dhcp = (root / 'config/dhcp').read_text()
        uci = (root / 'uci-defaults/90-f52-ap-client-r2').read_text()
        check_ap_network(network, dhcp, uci)
        with self.assertRaisesRegex(ValueError, 'DHCP/RA'):
            check_ap_network(network, dhcp.replace("option ra 'disabled'", "option ra 'server'"), uci)
        with self.assertRaisesRegex(ValueError, 'DHCP client'):
            check_ap_network(network.replace("option proto 'dhcp'", "option proto 'static'"), dhcp, uci)
        with self.assertRaisesRegex(ValueError, 'missing odhcpd'):
            check_ap_network(network, dhcp.replace("option maindhcp '0'", "option maindhcp '1'"), uci)


if __name__ == '__main__':
    unittest.main()
