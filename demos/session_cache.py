"""tracemalloc: distinguish a growing response cache from temporary batch memory."""

import argparse
from collections import OrderedDict
from pathlib import Path
import tracemalloc


MIB = 1024**2
CAPACITY = 64


def cache_response(cache, request_id, mode):
    payload = f"response:{request_id}".encode("ascii").ljust(32 * 1024, b".")
    cache[request_id] = payload
    if mode == "fast" and len(cache) > CAPACITY:
        cache.popitem(last=False)


def process_wave(cache, first_request, count, mode):
    # Scratch buffer owned by this wave. Release it before taking the snapshot.
    scratch = bytearray(4 * MIB)
    for offset in range(count):
        request_id = first_request + offset
        cache_response(cache, request_id, mode)
        scratch[offset % len(scratch)] = request_id & 255


def snapshot_of_demo():
    snapshot = tracemalloc.take_snapshot()
    return snapshot.filter_traces((tracemalloc.Filter(True, __file__),))


def main(mode, waves, wave_size):
    source = Path(__file__).read_text(encoding="utf-8").splitlines()
    tracemalloc.start(10)
    cache = OrderedDict()
    for request_id in range(CAPACITY):
        cache_response(cache, request_id, mode)
    previous = snapshot_of_demo()
    for wave in range(waves):
        tracemalloc.reset_peak()
        process_wave(cache, CAPACITY + wave * wave_size, wave_size, mode)
        current, peak = tracemalloc.get_traced_memory()
        after = snapshot_of_demo()
        differences = after.compare_to(previous, "lineno")
        net = sum(change.size_diff for change in differences)
        print(
            f"wave={wave + 1} entries={len(cache)} net={net / MIB:+.2f} MiB "
            f"traced_current={current / MIB:.2f} MiB phase_peak={peak / MIB:.2f} MiB"
        )
        for change in [item for item in differences if item.size_diff >= 1024][:3]:
            line = change.traceback[0].lineno
            print(
                f"  L{line} {change.size_diff / 1024:+.1f} KiB "
                f"blocks={change.count_diff:+d}: {source[line - 1].strip()}"
            )
        previous = after
    tracemalloc.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("slow", "fast"), default="slow")
    parser.add_argument("--waves", type=int, default=3)
    parser.add_argument("--wave-size", type=int, default=256)
    args = parser.parse_args()
    main(args.mode, args.waves, args.wave_size)
