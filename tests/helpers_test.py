import io
import os

import pytest

from binobj import helpers


def test_iter_bytes__zero():
    """Ensure max_bytes=0 yields no bytes.

    We should do this because the default value is None, and since 0 and None
    are both falsy, that might be an issue.
    """
    stream = io.BytesIO(b"abcdefg")
    result = list(helpers.iter_bytes(stream, 0))
    assert result == []
    assert stream.tell() == 0


@pytest.mark.parametrize("endian", ("big", "little"))
def test_write_int__endianness_default(monkeypatch, endian):
    """write_int should fall back to the system's endianness if it's not given.

    We test with both "big" and "little" so that this test does its job when run
    on either system.
    """
    monkeypatch.setattr(helpers.sys, "byteorder", endian)
    stream = io.BytesIO()
    helpers.write_int(stream, 65432, 2, signed=False)
    assert stream.getvalue() == int.to_bytes(65432, 2, byteorder=endian, signed=False)


@pytest.mark.parametrize("start,expected", ((0, b"qwertyu"), (9, b"p{}")))
def test_peek_bytes__basic(start, expected):
    stream = io.BytesIO(b"qwertyuiop{}|")

    assert stream.seek(start) == start
    assert helpers.peek_bytes(stream, len(expected)) == expected
    assert stream.tell() == start, "Stream position has moved."


@pytest.mark.parametrize("offset,expected", ((0, b""), (-3, b"{}|")))
def test_peek_bytes__short_read_okay_is_default(offset, expected):
    stream = io.BytesIO(b"qwertyuiop{}|")

    assert stream.seek(offset, os.SEEK_END) == 13 + offset
    assert helpers.peek_bytes(stream, len(expected) + 2) == expected
    assert stream.tell() == 13 + offset, "Stream position has moved."


@pytest.mark.parametrize("offset,expected", ((0, b"qwertyu"), (-3, b"[]|")))
def test_peek_bytes__short_read_crashes(offset, expected):
    """Throw EOFError if told to do so, and ensure that the stream pointer DOESN'T move
    on an error.
    """
    stream = io.BytesIO(b"qwertyuiop{}|")

    assert stream.seek(offset, os.SEEK_END) == 13 + offset
    with pytest.raises(EOFError):
        helpers.peek_bytes(stream, len(expected) + 2, False)

    assert stream.tell() == 13 + offset, "Stream position has moved"
