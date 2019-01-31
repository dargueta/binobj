"""An example using WAV audio."""

import io
import math
import wave

import binobj


class WAVFileHeader(binobj.Struct):
    riff_header = binobj.Bytes(const=b'RIFF')
    size = binobj.UInt32(endian='little')
    file_format = binobj.Bytes(const=b'WAVE')

    # Format and data chunks follow


class WAVFormatChunk(binobj.Struct):
    chunk_id = binobj.Bytes(const=b'fmt ')
    size = binobj.UInt32(const=16, endian='little')
    audio_format = binobj.UInt16(endian='little')
    n_channels = binobj.UInt16(endian='little')
    sample_rate = binobj.UInt32(endian='little')
    byte_rate = binobj.UInt32(endian='little')
    block_alignment = binobj.UInt16(endian='little')
    bits_per_sample = binobj.UInt16(endian='little')

    @byte_rate.computes
    def _byte_rate(self, all_fields):   # pylint: disable=no-self-use
        return (
            all_fields['sample_rate'] * all_fields['n_channels']
            * all_fields['bits_per_sample'] // 8)

    @block_alignment.computes
    def _block_alignment(self, all_fields):     # pylint: disable=no-self-use
        return all_fields['n_channels'] * all_fields['bits_per_sample'] // 8


class WAVDataChunk(binobj.Struct):
    chunk_id = binobj.Bytes(const=b'data')
    size = binobj.UInt32(endian='little')

    # WAV PCM data bytes follow.


def test_wav__basic_read(tmpdir):
    """Create 16-bit mono audio sampled at 8kHz and hope the header data we read
    back matches.
    """
    file_path = str(tmpdir.join('test.wav'))

    wav = wave.open(file_path, 'wb')
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
            this_frame.write(sample.to_bytes(2, 'little', signed=False))

        wav.writeframes(this_frame.getvalue())

        this_frame.seek(0)
        this_frame.truncate()
    wav.close()

    # Audio file has been written to test.wav. Now we need to read it back and
    # verify that we get sane values in the header. We're only checking the
    # header!
    with open(file_path, 'rb') as fd:
        file_header = WAVFileHeader.from_stream(fd)
        assert file_header.riff_header == b'RIFF'
        assert file_header.file_format == b'WAVE'

        format_chunk = WAVFormatChunk.from_stream(fd)
        assert format_chunk.size == 16, "Audio file isn't in PCM format."
        assert format_chunk.audio_format == 1, 'Audio data is compressed?'
        assert format_chunk.n_channels == 1
        assert format_chunk.sample_rate == 8000
        assert format_chunk.byte_rate == 16000
        assert format_chunk.block_alignment == 2
        assert format_chunk.bits_per_sample == 16

        data_chunk_header = WAVDataChunk.from_stream(fd)
        assert data_chunk_header.size == 64000


def test_wav__basic_write(tmpdir):
    """Write a 16-bit mono audio file sampled at 24kHz and try to read it back."""
    file_path = str(tmpdir.join('test.wav'))

    format_chunk = WAVFormatChunk(
        audio_format=1, n_channels=1, sample_rate=24000, bits_per_sample=16)

    # 24000 samples/s, 2 bytes/sample, 4s of audio = 192000B
    data_chunk = WAVDataChunk(size=192000)
    audio_data = b'\xaa\x55' * 96000

    header = WAVFileHeader(
        size=len(format_chunk) + len(data_chunk) + len(audio_data) + 4)

    with open(file_path, 'wb') as fd:
        header.to_stream(fd)
        format_chunk.to_stream(fd)
        data_chunk.to_stream(fd)
        fd.write(audio_data)

    wav = wave.open(file_path, 'rb')
    assert wav.getframerate() == 24000
    assert wav.getnchannels() == 1
    assert wav.getnframes() == 96000
    assert wav.getsampwidth() == 2
    wav.close()
