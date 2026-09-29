#!/usr/bin/env python3
"""Local validation and query plan for Point 6; AWS calls are opt-in in deploy_cleanup.py."""
from __future__ import annotations
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "dataset.csv"
REQUIRED = {"order_id", "customer_id", "region", "order_date", "amount", "status"}

FILTER_SQL = "SELECT order_id, customer_id, region, amount FROM orders WHERE status = 'paid' AND amount > 100"
GROUP_SQL = "SELECT region, COUNT(*) AS order_count, SUM(amount) AS total_amount FROM orders GROUP BY region"


def validate_csv(path: Path = CSV_PATH) -> dict[str, object]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 20:
        raise ValueError(f"dataset must have at least 20 rows, found {len(rows)}")
    if not rows or set(rows[0]) != REQUIRED:
        raise ValueError(f"unexpected CSV columns: {set(rows[0]) if rows else set()}")
    if len({r["order_id"] for r in rows}) != len(rows):
        raise ValueError("order_id must be unique in the seed dataset")
    for row in rows:
        float(row["amount"])
        if row["status"] not in {"paid", "pending", "cancelled"}:
            raise ValueError(f"invalid status: {row['status']}")
    return {"rows": len(rows), "columns": sorted(REQUIRED), "unique_order_ids": len(rows)}


def main() -> int:
    info = validate_csv()
    print(f"LOCAL VALIDATION: {info['rows']} CSV rows; columns={','.join(info['columns'])}")
    print("DRY-RUN (sin AWS):")
    print(f"  filter: {FILTER_SQL}")
    print(f"  group-by: {GROUP_SQL}")
    print("  append/update: upload a new CSV object, rerun crawler, then query again")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
