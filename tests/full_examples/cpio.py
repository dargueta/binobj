import datetime

import pytest

import binobj
from binobj import fields


class Timestamp32(binobj.UInt32):
    """A timestamp saved as an unsigned 32-bit integer with second resolution."""
    def _do_load(self, stream, context, loaded_fields):
        timestamp = super()._do_load(stream, context, loaded_fields)
        return datetime.datetime.fromtimestamp(timestamp)

    def _do_dump(self, stream, data, context, all_fields):
        if isinstance(data, (datetime.datetime, datetime.date)):
            data = int(data.timestamp())
        return super()._do_dump(stream, data, context, all_fields)


class CPIOFileHeader(binobj.Struct):
    magic = fields.UInt16(const=0o070707, discard=True, endian='little')
    device_id = fields.UInt16(default=0, endian='little')
    inumber = fields.UInt16(default=0, endian='little')
    mode = fields.UInt16(default=0o644, endian='little')
    owner_uid = fields.UInt16(default=0, endian='little')
    owner_gid = fields.UInt16(default=0, endian='little')
    n_links = fields.UInt16(default=0, endian='little')
    device_version = fields.UInt16(default=0, endian='little')
    modified_time = Timestamp32(default=datetime.datetime.now, endian='little')
    name_size = fields.UInt16(endian='little', discard=True)
    file_size = fields.UInt32(endian='little')
    filename = fields.StringZ(encoding='utf-8')
    _filename_padding = fields.Bytes(const=b'\0', discard=True,
                                     present=lambda f, *_: f['name_size'] % 2)
    data = fields.Bytes(size=file_size)

    @name_size.computes
    def _name_size(self, all_fields):
        return len((all_fields['filename'] + '\0').encode('utf-8'))

    @file_size.computes
    def _file_size(self, all_fields):
        return len(all_fields['data'])


@pytest.mark.parametrize('filename', ('evenlength.txt', 'oddlength.txt'))
def test_dump__even_size_filename(filename):
    filename_bytes = (filename + '\0').encode('utf-8')
    struct = CPIOFileHeader(filename=filename, data=b'0123',
                            modified_time=datetime.datetime.fromtimestamp(0xc0ffee))
    serialized = struct.to_bytes()

    assert serialized == (
        b'\xc7\x71'     # Magic
        b'\x00\x00'     # Device ID
        b'\x00\x00'     # inumber
        b'\xa4\x01'     # Mode
        b'\x00\x00'     # Owner UID
        b'\x00\x00'     # Owner GID
        b'\x00\x00'     # number of links
        b'\x00\x00'     # Device version
        b'\xee\xff\xc0\x00'     # Modified time
        + len(filename_bytes).to_bytes(2, 'little')     # Filename size
        + b'\x04\x00\x00\x00'   # File size
        + filename_bytes
        + (b'\0' * (len(filename_bytes) % 2))
        + b'0123'       # File contents
    )


@pytest.mark.parametrize('filename', ('evenlength.txt', 'oddlength.txt'))
def test_load__even_size_filename(filename):
    filename_bytes = (filename + '\0').encode('utf-8')

    serialized = (
        b'\xc7\x71'  # Magic
        b'\x80\x00'  # Device ID
        b'\xff\x7f'  # inumber
        b'\xa4\x01'  # Mode
        b'\x00\x00'  # Owner UID
        b'\x00\x00'  # Owner GID
        b'\x01\x00'  # number of links
        b'\x00\x00'  # Device version
        b'\x0d\xf0\xad\x0b'     # Modified time
        + len(filename_bytes).to_bytes(2, 'little')     # Filename size
        + b'\x04\x00\x00\x00'   # File size
        + filename_bytes
        + (b'\0' * (len(filename_bytes) % 2))
        + b'0123'  # File contents
    )

    struct = CPIOFileHeader.from_bytes(serialized)

    assert struct == {
        'device_id': 0x80,
        'inumber': 0x7fff,
        'mode': 0o644,
        'owner_uid': 0,
        'owner_gid': 0,
        'n_links': 1,
        'device_version': 0,
        'modified_time': datetime.datetime.fromtimestamp(0xbadf00d),
        'file_size': 4,
        'filename': filename,
        'data': b'0123',
    }
