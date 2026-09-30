#!/usr/bin/env python3
"""Punto 5 Redshift: upload CSVs and run a Data API workload.

The default mode is dry-run and performs no AWS calls. --execute is intentionally
required for any S3 or Redshift mutation. The admin password is read at runtime
from Secrets Manager only to validate the configured secret; it is never printed.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
TABLES = ("customers", "orders", "order_items")
SQL = {
    "customers": """CREATE TABLE IF NOT EXISTS customers (
        customer_id INTEGER NOT NULL PRIMARY KEY,
        full_name VARCHAR(120) NOT NULL,
        country CHAR(2) NOT NULL,
        signup_date DATE NOT NULL
    )""",
    "orders": """CREATE TABLE IF NOT EXISTS orders (
        order_id INTEGER NOT NULL PRIMARY KEY,
        customer_id INTEGER NOT NULL,
        order_date DATE NOT NULL,
        status VARCHAR(20) NOT NULL,
        total_amount DECIMAL(12,2) NOT NULL
    )""",
    "order_items": """CREATE TABLE IF NOT EXISTS order_items (
        order_item_id INTEGER NOT NULL PRIMARY KEY,
        order_id INTEGER NOT NULL,
        product VARCHAR(120) NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price DECIMAL(12,2) NOT NULL
    )""",
}
FILTER_SQL = """SELECT customer_id, full_name, country
FROM customers
WHERE country = 'CO'
ORDER BY customer_id"""
JOIN_SQL = """SELECT c.country, o.status, COUNT(*) AS order_count,
       SUM(o.total_amount) AS revenue
FROM customers c
JOIN orders o ON o.customer_id = c.customer_id
WHERE o.order_date >= DATE '2025-01-01'
GROUP BY c.country, o.status
ORDER BY revenue DESC"""
AGGREGATION_SQL = """SELECT o.order_id, SUM(i.quantity * i.unit_price) AS computed_total
FROM orders o
JOIN order_items i ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="perform AWS mutations (omitted = dry-run)")
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-2"))
    parser.add_argument("--bucket", default=os.getenv("REDSHIFT_S3_BUCKET"))
    parser.add_argument("--prefix", default=os.getenv("REDSHIFT_S3_PREFIX", "punto5/input"))
    parser.add_argument("--workgroup", default=os.getenv("REDSHIFT_WORKGROUP"))
    parser.add_argument("--database", default=os.getenv("REDSHIFT_DATABASE", "dev"))
    parser.add_argument("--secret-arn", default=os.getenv("REDSHIFT_SECRET_ARN"))
    parser.add_argument("--iam-auth", action="store_true", default=os.getenv("REDSHIFT_IAM_AUTH") == "1", help="use Data API IAM authentication (no SecretArn)")
    parser.add_argument("--copy-role-arn", default=os.getenv("REDSHIFT_COPY_ROLE_ARN"))
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    return parser.parse_args()


def csv_rows(path: Path) -> int:
    with path.open(newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def s3_uri(bucket: str, prefix: str, table: str) -> str:
    return f"s3://{bucket}/{prefix.strip('/')}/{table}.csv"


def get_secret(secretsmanager: Any, secret_arn: str) -> dict[str, Any]:
    response = secretsmanager.get_secret_value(SecretId=secret_arn)
    raw = response.get("SecretString")
    if not raw:
        raise ValueError("El secreto debe usar SecretString JSON; no se acepta secreto binario")
    value = json.loads(raw)
    if not isinstance(value, dict) or not value.get("username") or not value.get("password"):
        raise ValueError("El secreto debe contener username y password")
    # Deliberately do not return or log the password.
    return {"username": str(value["username"])}


def execute(data_api: Any, sql: str, args: argparse.Namespace) -> str:
    request = {
        "WorkgroupName": args.workgroup,
        "Database": args.database,
        "Sql": sql,
    }
    if not args.iam_auth:
        request["SecretArn"] = args.secret_arn
    response = data_api.execute_statement(**request)
    statement_id = response["Id"]
    while True:
        status = data_api.describe_statement(Id=statement_id)
        state = status["Status"]
        if state in {"FINISHED", "FAILED", "ABORTED"}:
            if state != "FINISHED":
                raise RuntimeError(f"Data API statement failed ({state}): {status.get('Error', 'sin detalle')}")
            return statement_id
        time.sleep(args.poll_seconds)


def results(data_api: Any, statement_id: str) -> list[list[Any]]:
    rows: list[list[Any]] = []
    token: str | None = None
    while True:
        request = {"Id": statement_id}
        if token:
            request["NextToken"] = token
        page = data_api.get_statement_result(**request)
        for record in page.get("Records", []):
            rows.append([next(iter(cell.values()), None) for cell in record])
        token = page.get("NextToken")
        if not token:
            return rows


def copy_sql(table: str, uri: str, role_arn: str) -> str:
    return (f"COPY {table} FROM '{uri}' IAM_ROLE '{role_arn}' "
            "CSV IGNOREHEADER 1 TIMEFORMAT 'auto' DATEFORMAT 'auto' TRUNCATECOLUMNS")


def main() -> int:
    args = parse_args()
    missing = [name for name, value in {
        "--bucket/REDSHIFT_S3_BUCKET": args.bucket,
        "--workgroup/REDSHIFT_WORKGROUP": args.workgroup,
        "--copy-role-arn/REDSHIFT_COPY_ROLE_ARN": args.copy_role_arn,
    }.items() if not value]
    if not args.iam_auth and not args.secret_arn:
        missing.append("--secret-arn/REDSHIFT_SECRET_ARN")
    if missing:
        raise ValueError("Faltan parámetros: " + ", ".join(missing))
    for table in TABLES:
        path = DATA_DIR / f"{table}.csv"
        print(f"{table}: {csv_rows(path)} filas; destino {s3_uri(args.bucket, args.prefix, table)}")
    print("Modo:", "EXECUTE (AWS)" if args.execute else "DRY-RUN (sin AWS)")
    if not args.execute:
        print("SQL DDL/COPY/consultas construido correctamente; use --execute solo con autorización.")
        return 0
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError("Instale boto3 para usar --execute; el dry-run no lo requiere") from exc

    session = boto3.Session(region_name=args.region)
    s3 = session.client("s3")
    secretsmanager = session.client("secretsmanager")
    data_api = session.client("redshift-data")
    if not args.iam_auth:
        get_secret(secretsmanager, args.secret_arn)
    for table in TABLES:
        s3.upload_file(str(DATA_DIR / f"{table}.csv"), args.bucket, f"{args.prefix.strip('/')}/{table}.csv")
    for table in TABLES:
        execute(data_api, SQL[table], args)
    for table in TABLES:
        execute(data_api, copy_sql(table, s3_uri(args.bucket, args.prefix, table), args.copy_role_arn), args)
    for label, sql in (("filter", FILTER_SQL), ("join", JOIN_SQL), ("aggregation", AGGREGATION_SQL)):
        statement_id = execute(data_api, sql, args)
        print(label, results(data_api, statement_id))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)

