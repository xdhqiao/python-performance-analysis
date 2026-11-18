"""Pyinstrument: latency of a checkout endpoint with three independent reads."""

import argparse
import asyncio
from contextlib import nullcontext
from pathlib import Path
from time import perf_counter, process_time


async def fetch_cart():
    await asyncio.sleep(0.36)
    return 12_500


async def fetch_shipping_quote():
    await asyncio.sleep(0.28)
    return 800


async def fetch_promotion():
    await asyncio.sleep(0.20)
    return 1_500


async def checkout(mode):
    if mode == "slow":
        subtotal = await fetch_cart()
        shipping = await fetch_shipping_quote()
        discount = await fetch_promotion()
    else:
        subtotal, shipping, discount = await asyncio.gather(
            fetch_cart(), fetch_shipping_quote(), fetch_promotion()
        )
    return subtotal + shipping - discount


async def run_requests(mode, requests):
    totals = []
    for _ in range(requests):
        totals.append(await checkout(mode))
    return totals


async def main(args):
    profiler = nullcontext()
    if args.html:
        from pyinstrument import Profiler

        profiler = Profiler(async_mode="enabled")

    wall_start, cpu_start = perf_counter(), process_time()
    with profiler:
        totals = await run_requests(args.mode, args.requests)
    wall, cpu = perf_counter() - wall_start, process_time() - cpu_start
    print(f"requests={len(totals)} total_cents={sum(totals)}")
    print(f"wall={wall:.3f}s cpu={cpu:.3f}s")
    if args.html:
        args.html.write_text(profiler.output_html(), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("slow", "fast"), default="slow")
    parser.add_argument("--requests", type=int, default=4)
    parser.add_argument("--html", type=Path)
    asyncio.run(main(parser.parse_args()))
