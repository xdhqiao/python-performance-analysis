"""Scalene: split a sensor pipeline into Python decoding and NumPy calibration."""

import argparse
from time import perf_counter

import numpy as np


def decode_gains(headers):
    gains = []
    for header in headers:
        digits = header.rsplit(b",", 1)[1]
        microgain = 0
        for digit in digits:
            if not 48 <= digit <= 57:
                raise ValueError("invalid gain field")
            microgain = microgain * 10 + (digit - 48)
        gains.append(microgain / 1_000_000)
    return gains


def calibrate_slow(frames, gain):
    copied = frames.copy()
    scaled = np.multiply(copied, gain)
    return np.add(scaled, np.float32(0.125))


def calibrate_fast(frames, gain, scratch):
    np.multiply(frames, gain, out=scratch)
    return np.add(scratch, np.float32(0.125), out=scratch)


def process_batches(mode, batches, side):
    rng = np.random.default_rng(42)
    frames = rng.random((side, side), dtype=np.float32)
    scratch = np.empty_like(frames) if mode == "fast" else None
    headers = tuple(
        f"sensor-{i},{1_000_000 + i % 31 * 1_000}".encode("ascii") for i in range(24_000)
    )
    checksum = 0.0
    for batch in range(batches):
        gains = decode_gains(headers)
        gain = np.float32(gains[batch % len(gains)])
        if mode == "slow":
            calibrated = calibrate_slow(frames, gain)
        else:
            calibrated = calibrate_fast(frames, gain, scratch)
        checksum += float(calibrated.mean(dtype=np.float64))
    return checksum


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("slow", "fast"), default="slow")
    parser.add_argument("--batches", type=int, default=64)
    parser.add_argument("--side", type=int, default=1_536)
    args = parser.parse_args()
    start = perf_counter()
    checksum = process_batches(args.mode, args.batches, args.side)
    print(f"batches={args.batches} checksum={checksum:.9f} wall={perf_counter() - start:.3f}s")
