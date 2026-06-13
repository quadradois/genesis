"""Níveis de áudio: RMS perceptual de chunks PCM int16 LE mono.

Usado para sincronizar o cérebro da Web UI com a voz real (spec §4.3):
o backend mede cada chunk e emite via hook opcional ui.on_audio_level().
"""
import math
from array import array


def rms_level(pcm: bytes) -> float:
    """RMS perceptual normalizado [0,1] de PCM int16 little-endian mono.

    Compressão por raiz quadrada (potência → percepção de volume) com ganho
    leve, para que fala em volume normal ocupe a faixa visual útil.
    """
    if len(pcm) < 2:
        return 0.0
    if len(pcm) % 2:
        pcm = pcm[:-1]
    samples = array("h")
    samples.frombytes(pcm)
    if not samples:
        return 0.0
    acc = 0
    for s in samples:
        acc += s * s
    rms = math.sqrt(acc / len(samples)) / 32767.0
    return min(1.0, math.sqrt(rms) * 1.2)
