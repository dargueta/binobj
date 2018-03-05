"""Some boot sector definitions for the FAT file system."""

import random

import binobj


class FAT12BootSector(binobj.Struct):
    jump = binobj.Bytes(size=3, default=b'\xeb\x3c\x90')
    oem_name = binobj.String(size=8, default='mkdosfs', pad_byte=b' ', encoding='ascii')
    bytes_per_sector = binobj.UInt16(default=512)
    sectors_per_cluster = binobj.UInt8()
    reserved_sectors = binobj.UInt16(default=1)
    num_fats = binobj.UInt8(default=2)
    max_root_entries = binobj.UInt16(default=240)
    total_logical_sectors_16 = binobj.UInt16()
    media_descriptor = binobj.UInt8()
    sectors_per_fat = binobj.UInt16()
    sectors_per_track = binobj.UInt16()
    num_heads = binobj.UInt16()
    num_hidden_sectors = binobj.UInt32(default=0)
    total_logical_sectors_32 = binobj.UInt32()
    drive_number = binobj.UInt8()
    _reserved = binobj.Bytes(default=b'\0', discard=True)
    _ex_boot_signature = binobj.Bytes(const=b'\x29', discard=True)
    volume_id = binobj.UInt32(default=lambda: random.randrange(2**32))
    volume_label = binobj.String(size=11)
    fs_type = binobj.String(size=8, default='FAT16', pad_byte=b' ', encoding='ascii')
    boot_code = binobj.Bytes(size=448, default=b'\xcc' * 448)
    boot_signature = binobj.Bytes(const=b'\x55\xaa')

    @property
    def total_logical_sectors(self):
        return self.total_logical_sectors_16 or self.total_logical_sectors_32

    @total_logical_sectors.setter
    def total_logical_sectors(self, total_sectors):
        if total_sectors < 1 or total_sectors >= 2**32:
            raise ValueError('Total sectors must be in [1, 2^32). Got: %d'
                             % total_sectors)
        elif total_sectors < 65535:
            self.total_logical_sectors_16 = total_sectors
            self.total_logical_sectors_32 = 0
        else:
            self.total_logical_sectors_16 = 0
            self.total_logical_sectors_32 = total_sectors


def test_fat12__basic():
    boot = FAT12BootSector(sectors_per_cluster=1, total_logical_sectors_16=1440,
                           media_descriptor=0xf0, sectors_per_fat=4,
                           sectors_per_track=36, num_heads=2,
                           total_logical_sectors_32=0, drive_number=0,
                           volume_id=0xdeadbeef, volume_label='abcdefghijk')

    assert bytes(boot) == (
        b'\xeb\x3c\x90mkdosfs \x00\x02\x01\x01\x00\x02\xf0\x00\xa0\x05\xf0\x04'
        b'\x00\x24\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x29\xef'
        b'\xbe\xad\xdeabcdefghijkFAT16   ' + (b'\xcc' * 448) + b'\x55\xaa')
