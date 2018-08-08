"""An example using a Windows BMP file."""

import io
import os

import pytest

import binobj


TEST_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')


class SimpleBMPFileHeader(binobj.Struct):
    """A class representing a specific kind of Windows Bitmap file (.bmp).

    For the sake of simplicity this spec assumes the file uses the legacy DIB
    header. Validation will fail if this isn't true, even if the BMP file itself
    is valid.
    """
    magic = binobj.Bytes(const=b'BM', discard=True)
    file_size = binobj.UInt32()
    _reserved = binobj.Bytes(const=b'\0\0\0\0', discard=True)
    pixels_offset = binobj.UInt32()

    # Legacy DIB header (BITMAPINFOHEADER)
    header_size = binobj.UInt32(const=40, discard=True)
    image_width = binobj.Int32()
    image_height = binobj.Int32()
    n_color_planes = binobj.UInt16(const=1)
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


def test_basic_bmp__loads(bmp_file):
    output = SimpleBMPFileHeader.from_bytes(bmp_file, exact=False)

    assert output.file_size == len(bmp_file)
    assert output.pixels_offset == 54
    assert output.image_width == 80
    assert output.image_height == 60
    assert output.n_color_planes == 1
    assert output.n_bits_per_pixel == 24
    assert output.compression_method == 0
    assert output.bitmap_size == 14400
    assert output.v_resolution == 2835
    assert output.h_resolution == 2835
    assert output.n_palette_colors == 0
    assert output.n_important_colors == 0


def test_basic_bmp__load(bmp_file):
    """Test loading from a stream."""
    stream = io.BytesIO(bmp_file)
    output = SimpleBMPFileHeader.from_stream(stream)

    assert output.file_size == len(bmp_file)
    assert output.pixels_offset == 54
    assert output.image_width == 80
    assert output.image_height == 60
    assert output.n_color_planes == 1
    assert output.n_bits_per_pixel == 24
    assert output.compression_method == 0
    assert output.bitmap_size == 14400
    assert output.v_resolution == 2835
    assert output.h_resolution == 2835
    assert output.n_palette_colors == 0
    assert output.n_important_colors == 0


def test_basic_bmp__dumps(bmp_file):
    """Writing the same data that's in the header should result in an identical
    header."""
    header_data = {
        'file_size': len(bmp_file),
        'pixels_offset': 54,
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

    loader = SimpleBMPFileHeader(**header_data)
    output = loader.to_bytes()

    assert len(output) == 54, 'Header is wrong size.'
    assert output == bmp_file[:54], 'Data mismatch.'
