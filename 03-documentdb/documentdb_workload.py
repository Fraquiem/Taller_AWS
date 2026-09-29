#!/usr/bin/env python3
"""Run the point-3 DocumentDB workload. Credentials come only from Secrets Manager."""
from __future__ import annotations
import argparse, json, os, ssl, tempfile
from pathlib import Path
from urllib.request import urlopen
import boto3
from pymongo import MongoClient

CA_URL = "https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem"
def secret_credentials(secret_id: str, region: str) -> tuple[str, str]:
    value = boto3.client("secretsmanager", region_name=region).get_secret_value(SecretId=secret_id)["SecretString"]
    payload = json.loads(value)
    if not isinstance(payload.get("username"), str) or not isinstance(payload.get("password"), str):
        raise ValueError("secret must contain string username and password")
    return payload["username"], payload["password"]

def ca_file(path: Path | None) -> str:
    if path:
        if not path.is_file(): raise FileNotFoundError(path)
        return str(path)
    target = Path(tempfile.gettempdir()) / "rds-global-bundle.pem"
    if not target.exists(): target.write_bytes(urlopen(CA_URL, timeout=30).read())
    return str(target)

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--secret-id", default=os.getenv("DOCDB_SECRET_ID"), required=False)
    p.add_argument("--endpoint", default=os.getenv("DOCDB_ENDPOINT"), required=False)
    p.add_argument("--port", type=int, default=int(os.getenv("DOCDB_PORT", "27018")))
    p.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-2"))
    p.add_argument("--ca-file", type=Path)
    p.add_argument("--tls-allow-invalid-hostname", action="store_true", help="Allow localhost SSH-tunnel hostname mismatch while retaining CA validation")
    p.add_argument("--database", default="eia_lab")
    args = p.parse_args()
    if not args.secret_id or not args.endpoint: p.error("--secret-id and --endpoint (or DOCDB_* env vars) are required")
    username, password = secret_credentials(args.secret_id, args.region)
    options = "&tlsAllowInvalidHostnames=true&directConnection=true" if args.tls_allow_invalid_hostname else ""
    uri = f"mongodb://{username}:{password}@{args.endpoint}:{args.port}/?tls=true&replicaSet=rs0&readPreference=secondaryPreferred&retryWrites=false{options}"
    client = MongoClient(uri, tlsCAFile=ca_file(args.ca_file), serverSelectionTimeoutMS=10000)
    collection = client[args.database]["students"]
    collection.delete_many({})
    documents = [{"student_id": i, "name": f"student-{i:02d}", "program": "data", "score": 60 + i * 3, "active": i % 2 == 0} for i in range(1, 11)]
    collection.insert_many(documents)
    filtered = list(collection.find({"active": True, "score": {"$gte": 70}}, {"_id": 0}).sort("score", -1))
    aggregation = list(collection.aggregate([{"$group": {"_id": "$program", "count": {"$sum": 1}, "average_score": {"$avg": "$score"}}}, {"$sort": {"average_score": -1}}]))
    print(json.dumps({"inserted": len(documents), "filter_count": len(filtered), "filter_sorted": filtered, "aggregation": aggregation}, default=str, indent=2))
    client.close()
    return 0
if __name__ == "__main__": raise SystemExit(main())
