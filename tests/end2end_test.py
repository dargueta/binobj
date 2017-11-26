"""End-to-end tests for the entire system."""

# pylint: disable=redefined-outer-names

import io
import os

import bitstring
import pytest

import binobj


TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')


class SimpleBMPFileHeader(binobj.Struct):
    """A class representing a specific kind of Windows Bitmap file (.bmp).

    For the sake of simplicity this spec assumes the file uses the legacy DIB
    header. Validation will fail if this isn't true, even if the BMP file itself
    is valid.
    """
    __options__ = {'endian': 'little'}

    magic = binobj.Bytes(const=b'BM')
    file_size = binobj.UInt32()
    _reserved = binobj.Bytes(n_bytes=4, discard=True, default=b'\0\0\0\0')
    pixels_offset = binobj.UInt32()

    # Legacy DIB header
    header_size = binobj.UInt32(const=40)
    image_width = binobj.Int32()
    image_height = binobj.Int32()
    n_color_planes = binobj.UInt16()
    n_bits_per_pixel = binobj.UInt16()
    compression_method = binobj.UInt32()
    bitmap_size = binobj.UInt32()
    v_resolution = binobj.Int32()
    h_resolution = binobj.Int32()
    n_palette_colors = binobj.UInt32()
    n_important_colors = binobj.UInt32()

    # Color palette starts here, if present. After that is the pixel data.


@pytest.fixture(scope='session')
def bmp_file():
    """Return the test bitmap file as :class:`bytes`."""
    with open(os.path.join(TEST_DATA_DIR, 'test_image.bmp'), 'rb') as fdesc:
        return fdesc.read()


@pytest.fixture(scope='session')
def png_file():
    """Return the test PNG file as :class:`bytes`."""
    with open(os.path.join(TEST_DATA_DIR, 'test_image.png'), 'rb') as fdesc:
        return fdesc.read()


def test_basic_bmp__loads(bmp_file):
    loader = SimpleBMPFileHeader()
    output = loader.loads(bmp_file)

    assert output == {
        'magic': b'BM',
        'file_size': len(bmp_file),
        'pixels_offset': 54,
        'header_size': 40,
        'image_width': 80,
        'image_height': 60,
        'n_color_planes': 1,
        'n_bits_per_pixel': 24,
        'compression_method': 0,
        'bitmap_size': 14400,
        'v_resolution': 2835,
        'h_resolution': 2835,
        'n_palette_colors': 0,
        'n_important_colors': 0,
    }


@pytest.mark.parametrize('constructor', (io.BytesIO, bitstring.ConstBitStream))
def test_basic_bmp__load(constructor, bmp_file):
    """Test loading from a stream, both a BytesIO and a ConstBitStream."""
    stream = constructor(bmp_file)
    loader = SimpleBMPFileHeader()
    output = loader.load(stream)

    assert output == {
        'magic': b'BM',
        'file_size': len(bmp_file),
        'pixels_offset': 54,
        'header_size': 40,
        'image_width': 80,
        'image_height': 60,
        'n_color_planes': 1,
        'n_bits_per_pixel': 24,
        'compression_method': 0,
        'bitmap_size': 14400,
        'v_resolution': 2835,
        'h_resolution': 2835,
        'n_palette_colors': 0,
        'n_important_colors': 0,
    }
