"""Some boot sector definitions for the FAT file system."""

from __future__ import annotations

import random

import binobj
from binobj import fields


class FAT12BootSector(binobj.Struct):
    jump = fields.Bytes(const=b"\xeb\x3c\x90")
    oem_name = fields.String(size=8, default="mkdosfs", pad_byte=b" ", encoding="ascii")
    bytes_per_sector = fields.UInt16(default=512)
    sectors_per_cluster = fields.UInt8()
    reserved_sectors = fields.UInt16(default=1)
    num_fats = fields.UInt8(default=2)
    max_root_entries = fields.UInt16(default=240)
    total_logical_sectors_16 = fields.UInt16()
    media_descriptor = fields.UInt8()
    sectors_per_fat = fields.UInt16()
    sectors_per_track = fields.UInt16()
    num_heads = fields.UInt16()
    num_hidden_sectors = fields.UInt32(default=0)
    total_logical_sectors_32 = fields.UInt32()
    drive_number = fields.UInt8()
    _reserved = fields.Bytes(const=b"\0", discard=True)
    _ex_boot_signature = fields.Bytes(const=b"\x29", discard=True)
    volume_id = fields.UInt32(factory=lambda: random.randrange(2**32))
    volume_label = fields.String(size=11)
    fs_type = fields.String(size=8, default="FAT12", pad_byte=b" ", encoding="ascii")
    boot_code = fields.Bytes(size=448, default=b"\xcc" * 448)
    boot_signature = fields.Bytes(const=b"\x55\xaa")

    @property
    def total_logical_sectors(self):
        return self.total_logical_sectors_16 or self.total_logical_sectors_32

    @total_logical_sectors.setter
    def total_logical_sectors(self, total_sectors):
        if total_sectors < 1 or total_sectors >= 2**32:
            raise ValueError(
                f"Total sectors must be in [1, 2^32). Got: {total_sectors!r}."
            )
        if total_sectors < 65535:
            self.total_logical_sectors_16 = total_sectors
            self.total_logical_sectors_32 = 0
        else:
            self.total_logical_sectors_16 = 0
            self.total_logical_sectors_32 = total_sectors


def test_fat12__basic():
    boot = FAT12BootSector(
        sectors_per_cluster=1,
        total_logical_sectors_16=1440,
        media_descriptor=0xF0,
        sectors_per_fat=4,
        sectors_per_track=36,
        num_heads=2,
        total_logical_sectors_32=0,
        drive_number=0,
        volume_id=0xDEADBEEF,
        volume_label="abcdefghijk",
    )

    assert bytes(boot) == (
        b"\xeb\x3c\x90mkdosfs \x00\x02\x01\x01\x00\x02\xf0\x00\xa0\x05\xf0\x04"
        b"\x00\x24\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x29\xef"
        b"\xbe\xad\xdeabcdefghijkFAT12   " + (b"\xcc" * 448) + b"\x55\xaa"
    )
