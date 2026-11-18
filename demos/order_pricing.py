"""cProfile: price a stream of orders against a fixed regional rule set."""

import argparse
import json
from time import perf_counter


RULES = '{"north": [700, 450], "south": [850, 350], "west": [625, 550]}'
REGIONS = ("north", "south", "west")


def read_rules():
    return json.loads(RULES)


def price_order(subtotal, region, rules):
    tax_bps, shipping_cents = rules[region]
    tax_cents = (subtotal * tax_bps + 5_000) // 10_000
    return subtotal + tax_cents + (shipping_cents if subtotal < 20_000 else 0)


def price_batch_slow(orders):
    total = 0
    for subtotal, region in orders:
        total += price_order(subtotal, region, read_rules())
    return total


def price_batch_fast(orders):
    rules = read_rules()
    total = 0
    for subtotal, region in orders:
        total += price_order(subtotal, region, rules)
    return total


def make_orders(count):
    return [(500 + (index * 137) % 40_000, REGIONS[index % 3]) for index in range(count)]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("slow", "fast"), default="slow")
    parser.add_argument("--orders", type=int, default=180_000)
    args = parser.parse_args()
    orders = make_orders(args.orders)
    price_batch = price_batch_slow if args.mode == "slow" else price_batch_fast
    start = perf_counter()
    total = price_batch(orders)
    print(f"orders={len(orders)} total_cents={total} batch_wall={perf_counter() - start:.3f}s")
