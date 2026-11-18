"""Memray: locate a transient native heap peak while aggregating daily arrays."""

import argparse
from time import perf_counter

import numpy as np


def load_day(day, cells):
    # A synthetic dense grid standing in for one decoded day's data.
    return (np.arange(cells, dtype=np.int32) % 1_000) + day


def materialize_report(days, cells):
    daily = [load_day(day, cells) for day in range(days)]
    cube = np.stack(daily)
    return cube.sum(axis=0, dtype=np.int64)


def stream_report(days, cells):
    totals = np.zeros(cells, dtype=np.int64)
    for day in range(days):
        totals += load_day(day, cells)
    return totals


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("slow", "fast"), default="slow")
    parser.add_argument("--days", type=int, default=10)
    parser.add_argument("--cells", type=int, default=1_048_576)
    args = parser.parse_args()
    report = materialize_report if args.mode == "slow" else stream_report
    start = perf_counter()
    totals = report(args.days, args.cells)
    print(f"cells={len(totals)} checksum={totals.sum()} wall={perf_counter() - start:.3f}s")
