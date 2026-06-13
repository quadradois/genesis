import math
import struct

from core.audio_levels import rms_level


def _sine(amplitude: float, n: int = 1024) -> bytes:
    return b"".join(
        struct.pack("<h", int(amplitude * 32767 * math.sin(2 * math.pi * i / 64)))
        for i in range(n)
    )


def test_silencio_e_vazio():
    assert rms_level(b"") == 0.0
    assert rms_level(b"\x00" * 2048) == 0.0


def test_senoide_cheia_satura_em_1():
    assert rms_level(_sine(1.0)) > 0.95


def test_meia_amplitude_intermediario():
    lvl = rms_level(_sine(0.5))
    assert 0.6 < lvl < 0.8


def test_monotonico():
    assert rms_level(_sine(0.1)) < rms_level(_sine(0.4)) < rms_level(_sine(0.9))


def test_bytes_impares_nao_explodem():
    assert 0.0 <= rms_level(_sine(0.5) + b"\x01") <= 1.0
