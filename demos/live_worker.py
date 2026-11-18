"""py-spy: attach to a running worker that groups semi-structured product tags."""

import argparse
import os
from collections import Counter
from time import perf_counter, sleep


def normalize_tag(raw_tag):
    return "-".join(raw_tag.strip().casefold().replace("_", " ").split())


def summarize_batch(raw_tags, mode):
    summary = Counter()
    if mode == "slow":
        for raw_tag in raw_tags:
            summary[normalize_tag(raw_tag)] += 1
    else:
        for raw_tag, count in Counter(raw_tags).items():
            summary[normalize_tag(raw_tag)] += count
    return summary


def make_batch():
    categories = ("Sport_Watch", "Sport Watch", "Trail Shoes", "USB_C", "USB C")
    return tuple(
        f"  {categories[index % len(categories)]}  series {index % 64}  "
        for index in range(60_000)
    )


def main(mode, seconds):
    raw_tags = make_batch()
    batches = 0
    start = perf_counter()
    deadline = start + seconds
    print(f"pid={os.getpid()} mode={mode} duration={seconds}s", flush=True)
    while perf_counter() < deadline:
        summary = summarize_batch(raw_tags, mode)
        batches += 1
        sleep(0.005)  # Stand-in for waiting for the next batch.
    elapsed = perf_counter() - start
    if batches:
        print(
            f"batches={batches} tags_per_second={batches * len(raw_tags) / elapsed:,.0f} "
            f"groups={len(summary)} tags_per_batch={summary.total()}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("slow", "fast"), default="slow")
    parser.add_argument("--seconds", type=float, default=90)
    args = parser.parse_args()
    main(args.mode, args.seconds)
