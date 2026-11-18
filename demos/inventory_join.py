"""line_profiler: reconcile a batch of sales against a product catalog."""

import argparse
from time import perf_counter

from line_profiler import profile


@profile
def reconcile_slow(sales, catalog):
    revenue = missing = 0
    for sku, quantity in sales:
        unit_price = None
        for candidate, candidate_price in catalog:
            if candidate == sku:
                unit_price = candidate_price
                break
        if unit_price is None:
            missing += 1
            continue
        revenue += quantity * unit_price
    return revenue, missing


@profile
def reconcile_fast(sales, catalog):
    prices = dict(catalog)  # Catalog SKUs are unique.
    revenue = missing = 0
    for sku, quantity in sales:
        unit_price = prices.get(sku)
        if unit_price is None:
            missing += 1
            continue
        revenue += quantity * unit_price
    return revenue, missing


def make_data(size, transactions):
    catalog = [(f"SKU-{i:05}", 100 + i % 600) for i in range(size)]
    sales = [
        (f"SKU-{i * 37 % (size + 19):05}", 1 + i % 7) for i in range(transactions)
    ]
    return sales, catalog


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("slow", "fast"), default="slow")
    parser.add_argument("--skus", type=int, default=2_000)
    parser.add_argument("--transactions", type=int, default=2_500)
    args = parser.parse_args()
    data = make_data(args.skus, args.transactions)
    reconcile = reconcile_slow if args.mode == "slow" else reconcile_fast
    start = perf_counter()
    revenue, missing = reconcile(*data)
    print(f"revenue_cents={revenue} missing={missing} batch_wall={perf_counter() - start:.3f}s")
