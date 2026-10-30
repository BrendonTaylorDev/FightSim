"""Make the starter breathing sounds (build 329; in sound_starters/ since build 331): panting and the long breath back
in, from shaped noise. They are placeholders, used only for a kind with no files of your own in sounds/<kind>/.
Run: python sim/make_breath_sounds.py"""
import math
import os
import random
import struct
import wave

RATE = 22050
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sound_starters")


def breath(dur, loud, bright, rng, rough=0.0):
    """One breath (in or out): noise through two one-pole filters (a soft band), under a rise-and-fall envelope."""
    n = int(dur * RATE)
    out, lp1, lp2 = [], 0.0, 0.0
    a1, a2 = bright, bright * 0.25
    for i in range(n):
        x = rng.uniform(-1, 1)
        lp1 += a1 * (x - lp1)
        lp2 += a2 * (lp1 - lp2)
        band = lp1 - lp2
        t = i / max(1, n - 1)
        env = math.sin(math.pi * t) ** 1.5
        if rough:
            env *= 1.0 - rough * (0.5 + 0.5 * math.sin(2 * math.pi * 9 * t + rng.random()))
        out.append(band * env * loud)
    return out


def write(path, samples):
    peak = max(1e-6, max(abs(s) for s in samples))
    k = 0.6 / peak
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s * k)) * 32767)) for s in samples))


def silence(sec):
    return [0.0] * int(sec * RATE)


def main():
    for k in ("pant", "breath_back"):
        os.makedirs(os.path.join(OUT, k), exist_ok=True)
    for v in range(3):
        rng = random.Random(100 + v)
        s = []
        for _ in range(3):
            s += breath(rng.uniform(0.22, 0.3), 1.0, 0.35, rng) + silence(0.04)
            s += breath(rng.uniform(0.25, 0.34), 0.8, 0.25, rng) + silence(rng.uniform(0.05, 0.1))
        write(os.path.join(OUT, "pant", f"pant_{v + 1}.wav"), s)
    for v in range(2):
        rng = random.Random(200 + v)
        s = breath(1.1 + 0.2 * v, 1.0, 0.3, rng, rough=0.6) + silence(0.15) + breath(0.9, 0.6, 0.2, rng)
        write(os.path.join(OUT, "breath_back", f"breath_back_{v + 1}.wav"), s)


if __name__ == "__main__":
    main()
