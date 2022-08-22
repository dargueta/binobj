import datetime
import functools

import pytest

import binobj
from binobj import fields


_NOW = functools.partial(datetime.datetime.now, datetime.timezone.utc)


class CPIOFileHeader(binobj.Struct):
    class Meta:
        argument_defaults = {
            "endian": "little",
        }

    magic = fields.UInt16(const=0o070707, discard=True)
    device_id = fields.UInt16(default=0)
    inumber = fields.UInt16(default=0)
    mode = fields.UInt16(default=0o644)
    owner_uid = fields.UInt16(default=0)
    owner_gid = fields.UInt16(default=0)
    n_links = fields.UInt16(default=0)
    device_version = fields.UInt16(default=0)
    modified_time = fields.Timestamp32(factory=_NOW, tz_aware=True)
    name_size = fields.UInt16()
    file_size = fields.UInt32()
    filename = fields.StringZ(encoding="utf-8")
    _filename_padding = fields.Bytes(
        const=b"\0", discard=True, present=lambda f, *_: f["name_size"] % 2
    )
    data = fields.Bytes(size=file_size)

    @name_size.computes
    def _name_size(self, all_fields):
        return len((all_fields["filename"] + "\0").encode("utf-8"))

    @file_size.computes
    def _file_size(self, all_fields):
        return len(all_fields["data"])


@pytest.mark.parametrize("filename", ("evenlength.txt", "oddlength.txt"))
def test_dump__padding_null_behaves(filename):
    filename_bytes = (filename + "\0").encode("utf-8")
    file_data = b"0123456789"
    when = datetime.datetime.fromtimestamp(0xC0FFEE, datetime.timezone.utc)

    struct = CPIOFileHeader(filename=filename, data=file_data, modified_time=when)
    serialized = struct.to_bytes()

    assert serialized == (
        b"\xc7\x71"  # Magic
        b"\x00\x00"  # Device ID
        b"\x00\x00"  # inumber
        b"\xa4\x01"  # Mode
        b"\x00\x00"  # Owner UID
        b"\x00\x00"  # Owner GID
        b"\x00\x00"  # number of links
        b"\x00\x00"  # Device version
        + int(when.timestamp()).to_bytes(4, "little")  # Modified time
        + len(filename_bytes).to_bytes(2, "little")  # Filename size
        + len(file_data).to_bytes(4, "little")  # File size
        + filename_bytes
        + (b"\0" * (len(filename_bytes) % 2))
        + file_data  # File contents
    )


@pytest.mark.parametrize("filename", ("evenlength.txt", "oddlength.txt"))
def test_load__padding_null_behaves(filename):
    filename_bytes = (filename + "\0").encode("utf-8")
    file_data = b"0123456789"
    when = datetime.datetime.fromtimestamp(0xBADF00D, datetime.timezone.utc)

    serialized = (
        b"\xc7\x71"  # Magic
        b"\x80\x00"  # Device ID
        b"\xff\x7f"  # inumber
        b"\xa4\x01"  # Mode
        b"\x00\x00"  # Owner UID
        b"\x00\x00"  # Owner GID
        b"\x01\x00"  # number of links
        b"\x00\x00"  # Device version
        + int(when.timestamp()).to_bytes(4, "little")  # Modified time
        + len(filename_bytes).to_bytes(2, "little")  # Filename size
        + len(file_data).to_bytes(4, "little")  # File size
        + filename_bytes
        + (b"\0" * (len(filename_bytes) % 2))
        + file_data  # File contents
    )

    struct = CPIOFileHeader.from_bytes(serialized)

    assert struct.to_dict() == {
        "device_id": 0x80,
        "inumber": 0x7FFF,
        "mode": 0o644,
        "owner_uid": 0,
        "owner_gid": 0,
        "n_links": 1,
        "device_version": 0,
        "modified_time": when,
        "name_size": len(filename) + 1,  # (name_size includes trailing null)
        "file_size": len(file_data),
        "filename": filename,
        "data": file_data,
    }
