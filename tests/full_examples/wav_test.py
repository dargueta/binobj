"""An example using WAV audio."""

from __future__ import annotations

import io
import math
import wave
from typing import TYPE_CHECKING

import binobj
from binobj import fields


if TYPE_CHECKING:  # pragma: no cover
    import pathlib
    from typing import ClassVar


class WAVFileHeader(binobj.Struct):
    riff_header = fields.Bytes(const=True, default=b"RIFF")
    size = fields.UInt32(endian="little")
    file_format = fields.Bytes(const=True, default=b"WAVE")

    # Format and data chunks follow


class WAVFormatChunk(binobj.Struct):
    class Meta:
        argument_defaults: ClassVar = {
            "endian": "little",
        }

    chunk_id = fields.Bytes(const=True, default=b"fmt ")
    size = fields.UInt32(const=True, default=16)
    audio_format = fields.UInt16()
    n_channels = fields.UInt16()
    sample_rate = fields.UInt32()
    byte_rate = fields.UInt32()
    block_alignment = fields.UInt16()
    bits_per_sample = fields.UInt16()

    @byte_rate.computes
    def _byte_rate(self, all_fields):
        return (
            all_fields["sample_rate"]
            * all_fields["n_channels"]
            * all_fields["bits_per_sample"]
            // 8
        )

    @block_alignment.computes
    def _block_alignment(self, all_fields):
        return all_fields["n_channels"] * all_fields["bits_per_sample"] // 8


class WAVDataChunk(binobj.Struct):
    chunk_id = fields.Bytes(const=True, default=b"data")
    size = fields.UInt32(endian="little")
    audio_data = fields.Bytes(size=size)

    @size.computes
    def _size(self, all_fields):
        return len(all_fields["audio_data"])


def test_wav__basic_read(tmp_path: pathlib.Path) -> None:
    """Create 16-bit mono audio sampled at 8kHz and hope the header data we read
    back matches.
    """
    file_path = tmp_path / "test.wav"

    with file_path.open("wb") as fd, wave.open(fd, "wb") as wav:
        wav.setnchannels(1)
        wav.setframerate(8000)
        wav.setsampwidth(2)

        # Write 4 seconds of audio, each second with a different tone. One frame is
        # 16 bits, 8000 frames per second -> 16000 bytes per second. Total: 64000
        this_frame = io.BytesIO()

        for herz in (440, 540, 640, 740):
            for frame_i in range(8000):
                theta = (frame_i / 8000) * (2 * math.pi) * herz
                sample = int(16384 * math.sin(theta)) + 16384
                this_frame.write(sample.to_bytes(2, "little", signed=False))

            wav.writeframes(this_frame.getvalue())

            this_frame.seek(0)
            this_frame.truncate()

    # Audio file has been written to test.wav. Now we need to read it back and
    # verify that we get sane values in the header. We're only checking the
    # header!
    with file_path.open("rb") as fd:
        file_header = WAVFileHeader.from_stream(fd)
        assert file_header.riff_header == b"RIFF"
        assert file_header.file_format == b"WAVE"

        format_chunk = WAVFormatChunk.from_stream(fd)
        assert format_chunk.size == 16, "Audio file isn't in PCM format."
        assert format_chunk.audio_format == 1, "Audio data is compressed?"
        assert format_chunk.n_channels == 1
        assert format_chunk.sample_rate == 8000
        assert format_chunk.byte_rate == 16000
        assert format_chunk.block_alignment == 2
        assert format_chunk.bits_per_sample == 16

        data_chunk_header = WAVDataChunk.from_stream(fd)
        assert data_chunk_header.size == 64000
        assert len(data_chunk_header.audio_data) == data_chunk_header.size


def test_wav__basic_write(tmp_path: pathlib.Path):
    """Write a 16-bit mono audio file sampled at 24kHz and try to read it back."""
    file_path = tmp_path / "test.wav"

    format_chunk = WAVFormatChunk(
        audio_format=1, n_channels=1, sample_rate=24000, bits_per_sample=16
    )

    # 24000 samples/s, 2 bytes/sample, 4s of audio = 192000B
    data_chunk = WAVDataChunk(audio_data=b"\xaa\x55" * 96000)
    header = WAVFileHeader(size=len(format_chunk) + len(data_chunk))

    with file_path.open("wb") as fd:
        header.to_stream(fd)
        format_chunk.to_stream(fd)
        data_chunk.to_stream(fd)
        fd.write(data_chunk.audio_data)

    with file_path.open("rb") as fd, wave.open(fd, "rb") as wav:
        assert wav.getframerate() == 24000
        assert wav.getnchannels() == 1
        assert wav.getnframes() == 96000
        assert wav.getsampwidth() == 2
