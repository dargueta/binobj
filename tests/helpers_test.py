import io

import pytest

from binobj import helpers


def test_iter_bytes__zero():
    """Ensure max_bytes=0 yields no bytes.

    We should do this because the default value is None, and since 0 and None
    are both falsy, that might be an issue.
    """
    stream = io.BytesIO(b'abcdefg')
    result = list(helpers.iter_bytes(stream, 0))
    assert result == []
    assert stream.tell() == 0


@pytest.mark.parametrize('endian', ('big', 'little'))
def test_write_int__endianness_default(monkeypatch, endian):
    """write_int should fall back to the system's endianness if it's not given.

    We test with both "big" and "little" so that this test does its job when run
    on either system.
    """
    monkeypatch.setattr(helpers.sys, 'byteorder', endian)
    stream = io.BytesIO()
    helpers.write_int(stream, 65432, 2, signed=False)
    assert stream.getvalue() == int.to_bytes(65432, 2, byteorder=endian, signed=False)
