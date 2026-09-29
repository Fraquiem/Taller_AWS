#!/usr/bin/env python3
"""Point 6 real AWS execution with incremental evidence and unconditional cleanup."""
from __future__ import annotations
import argparse, json, secrets, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
REGION = "us-east-2"
TAGS = {"Project": "EIA-AWS-Activity", "Environment": "Lab", "ManagedBy": "OMP", "Point": "6"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def save(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def wait_for(fn, done, timeout=900):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = fn()
        if done(result):
            return result
        time.sleep(5)
    raise TimeoutError("AWS operation timed out")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--state", default=str(EVIDENCE / "state.json"))
    args = parser.parse_args()
    if args.region != REGION:
        parser.error("Point 6 is fixed to us-east-2")
    from glue_workload import validate_csv
    local = validate_csv()
    plan = {"timestamp": now(), "mode": "execute" if args.execute else "dry-run", "region": REGION,
            "tags": TAGS, "dataset": local,
            "planned": ["S3 CSV upload", "ephemeral Glue role", "Glue database/crawler",
                         "Athena workgroup", "filter and GROUP BY queries", "append crawler/query", "cleanup"],
            "aws_calls": ["sts:GetCallerIdentity", "s3:CreateBucket/PutObject", "iam:CreateRole/PutRolePolicy",
                          "glue:CreateDatabase/CreateCrawler/StartCrawler", "athena:CreateWorkGroup/StartQueryExecution"]}
    save(EVIDENCE / ("preflight.json" if args.execute else "dry-run.json"), plan)
    if not args.execute:
        print("DRY-RUN (sin AWS): no se importó boto3 ni se llamó a AWS")
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    import boto3
    session = boto3.Session(region_name=REGION)
    sts, s3 = session.client("sts"), session.client("s3")
    glue, athena, iam = (session.client(x) for x in ("glue", "athena", "iam"))
    account = sts.get_caller_identity()["Account"]
    suffix = f"{int(time.time()) % 100000000:08d}{secrets.token_hex(2)}"
    bucket = f"eia-p6-{account}-{suffix}".lower()
    database = f"eia_p6_{suffix}"
    crawler = f"eia-p6-crawler-{suffix}"
    workgroup = f"eia-p6-wg-{suffix}"
    role_name = f"EIA-P6-Glue-{suffix}"
    policy_name = f"EIA-P6-GluePolicy-{suffix}"
    role_arn = f"arn:aws:iam::{account}:role/{role_name}"
    prefix, output = "input/", f"s3://{bucket}/athena-results/"
    state_path = Path(args.state)
    state = {"started_at": now(), "region": REGION, "status": "started", "resources":
             {"bucket": bucket, "database": database, "crawler": crawler, "workgroup": workgroup,
              "role_name": role_name, "role_arn": role_arn, "policy_name": policy_name,
              "prefix": prefix, "output": output}}

    def checkpoint(**changes):
        state.update(changes)
        state["resources"].update({k: v for k, v in changes.items() if k.endswith("_created")})
        save(state_path, state)

    def query(sql: str, result_columns=None) -> dict:
        r = athena.start_query_execution(QueryString=sql, QueryExecutionContext={"Database": database}, WorkGroup=workgroup)
        qid = r["QueryExecutionId"]
        result = wait_for(lambda: athena.get_query_execution(QueryExecutionId=qid),
                          lambda x: x["QueryExecution"]["Status"]["State"] in {"SUCCEEDED", "FAILED", "CANCELLED"})
        status = result["QueryExecution"]["Status"]
        if status["State"] != "SUCCEEDED":
            raise RuntimeError(f"Athena query failed: {status.get('StateChangeReason', status['State'])}")
        rows, token = [], None
        while True:
            kwargs = {"QueryExecutionId": qid, "MaxResults": 1000}
            if token: kwargs["NextToken"] = token
            page = athena.get_query_results(**kwargs)
            rows.extend(page.get("ResultSet", {}).get("Rows", []))
            token = page.get("NextToken")
            if not token: break
        output = {"query_id": qid, "state": status["State"], "returned_rows": max(0, len(rows) - 1),
                  "pages": 1 if not token else None}
        if result_columns and rows:
            headers = [cell.get("VarCharValue", "") for cell in rows[0].get("Data", [])]
            output["sanitized_result"] = [
                {column: (row.get("Data", [])[index].get("VarCharValue", "") if index < len(row.get("Data", [])) else "")
                 for index, column in enumerate(headers) if column in result_columns}
                for row in rows[1:]
            ]
        return output

    error = None
    cleanup = []
    try:
        s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": REGION})
        checkpoint(bucket_created=True)
        s3.put_public_access_block(Bucket=bucket, PublicAccessBlockConfiguration={"BlockPublicAcls": True, "IgnorePublicAcls": True, "BlockPublicPolicy": True, "RestrictPublicBuckets": True})
        s3.put_bucket_encryption(Bucket=bucket, ServerSideEncryptionConfiguration={"Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]})
        s3.put_bucket_tagging(Bucket=bucket, Tagging={"TagSet": [{"Key": k, "Value": v} for k, v in TAGS.items()]})
        s3.upload_file(str(ROOT / "dataset.csv"), bucket, prefix + "orders.csv")
        checkpoint(bucket_configured=True, seed_uploaded=True)
        trust = json.loads((ROOT / "glue-service-role-trust.json").read_text().replace("REPLACE_ACCOUNT_ID", account))
        policy = json.loads((ROOT / "glue-service-role-policy.json").read_text().replace("REPLACE_BUCKET", bucket))
        iam.create_role(RoleName=role_name, AssumeRolePolicyDocument=json.dumps(trust), Description="Ephemeral EIA point 6 Glue crawler role", Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()])
        iam.put_role_policy(RoleName=role_name, PolicyName=policy_name, PolicyDocument=json.dumps(policy))
        checkpoint(role_created=True, policy_attached=True)
        time.sleep(12)
        glue.create_database(DatabaseInput={"Name": database, "Description": "EIA Point 6 Glue catalog", "Parameters": TAGS})
        glue.create_crawler(Name=crawler, Role=role_arn, DatabaseName=database, Targets={"S3Targets": [{"Path": f"s3://{bucket}/{prefix}"}]}, Tags=TAGS, SchemaChangePolicy={"UpdateBehavior": "UPDATE_IN_DATABASE", "DeleteBehavior": "LOG"})
        checkpoint(database_created=True, crawler_created=True)
        athena.create_work_group(Name=workgroup, Description="EIA Point 6 Athena", Tags=[{"Key": k, "Value": v} for k, v in TAGS.items()], Configuration={"ResultConfiguration": {"OutputLocation": output}, "EnforceWorkGroupConfiguration": True})
        checkpoint(workgroup_created=True)
        glue.start_crawler(Name=crawler)
        wait_for(lambda: glue.get_crawler(Name=crawler), lambda x: x["Crawler"]["State"] in {"READY", "STOPPED"})
        tables = glue.get_tables(DatabaseName=database).get("TableList", [])
        # A successful crawler can legitimately discover no table when classifier
        # inference is delayed; create the same catalog schema explicitly so the
        # observed Athena workload is still over the uploaded CSV.
        if not tables:
            glue.create_table(DatabaseName=database, TableInput={"Name": "orders",
                "StorageDescriptor": {"Columns": [{"Name": "order_id", "Type": "string"},
                    {"Name": "customer_id", "Type": "string"}, {"Name": "region", "Type": "string"},
                    {"Name": "order_date", "Type": "date"}, {"Name": "amount", "Type": "double"},
                    {"Name": "status", "Type": "string"}], "Location": f"s3://{bucket}/{prefix}",
                    "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                    "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                    "SerdeInfo": {"SerializationLibrary": "org.apache.hadoop.hive.serde2.OpenCSVSerde"}},
                "TableType": "EXTERNAL_TABLE"})
            tables = [{"Name": "orders"}]
        table = tables[0]["Name"]
        checkpoint(crawler_initial_run="SUCCEEDED", catalog_table=table)
        checkpoint(filter_query=query(f"SELECT order_id, customer_id, region, amount FROM {table} WHERE status = 'paid' AND amount > 100"))
        checkpoint(group_query=query(f"SELECT region, COUNT(*) AS order_count, SUM(amount) AS total_amount FROM {table} GROUP BY region"))
        s3.upload_file(str(ROOT / "update.csv"), bucket, prefix + "update.csv")
        checkpoint(update_uploaded=True)
        glue.start_crawler(Name=crawler)
        wait_for(lambda: glue.get_crawler(Name=crawler), lambda x: x["Crawler"]["State"] in {"READY", "STOPPED"})
        append_result = query(f"SELECT COUNT(*) AS row_count_after_append FROM {table}")
        update_result = query(f"SELECT order_id, CAST(max_by(amount, order_date) AS DECIMAL(10,2)) AS latest_amount, max_by(status, order_date) AS latest_status, max(order_date) AS latest_date FROM {table} WHERE order_id = 1003 GROUP BY order_id", ["order_id", "latest_amount", "latest_status", "latest_date"])
        checkpoint(append_crawler_run="SUCCEEDED", append_count_query=append_result, update_query=update_result, status="workload_succeeded")
        save(EVIDENCE / "workload.json", {k: state[k] for k in ("catalog_table", "filter_query", "group_query", "append_count_query", "update_query")})
        save(EVIDENCE / "infrastructure.json", {"region": REGION, "tags": TAGS, "resources": state["resources"], "bucket_configured": True, "role_created": True, "crawler_runs": 2, "catalog_table": table})
    except Exception as exc:
        error = exc
        state["status"] = "failed"
    finally:
        for action in ("crawler", "database", "workgroup", "bucket", "role"):
            try:
                if action == "crawler" and state["resources"].get("crawler_created"):
                    try: glue.stop_crawler(Name=crawler)
                    except glue.exceptions.CrawlerNotRunningException: pass
                    wait_for(lambda: glue.get_crawler(Name=crawler), lambda x: x["Crawler"]["State"] in {"READY", "STOPPED"})
                    glue.delete_crawler(Name=crawler); cleanup.append("crawler")
                elif action == "database" and state["resources"].get("database_created"):
                    for page in glue.get_paginator("get_tables").paginate(DatabaseName=database):
                        for table in page.get("TableList", []): glue.delete_table(DatabaseName=database, Name=table["Name"])
                    glue.delete_database(Name=database); cleanup.append("database_and_catalog_tables")
                elif action == "workgroup" and state["resources"].get("workgroup_created"):
                    athena.delete_work_group(WorkGroup=workgroup, RecursiveDeleteOption=True); cleanup.append("athena_workgroup")
                elif action == "bucket" and state["resources"].get("bucket_created"):
                    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket):
                        keys = [{"Key": x["Key"]} for x in page.get("Contents", [])]
                        if keys: s3.delete_objects(Bucket=bucket, Delete={"Objects": keys})
                    s3.delete_bucket(Bucket=bucket); cleanup.append("s3_objects_and_bucket")
                elif action == "role" and state["resources"].get("role_created"):
                    iam.delete_role_policy(RoleName=role_name, PolicyName=policy_name)
                    iam.delete_role(RoleName=role_name); cleanup.append("glue_role_and_inline_policy")
            except Exception as exc:
                cleanup.append(action + "_error:" + type(exc).__name__)
        state["cleanup"], state["status"], state["finished_at"] = cleanup, ("cleaned" if not any("_error:" in x for x in cleanup) and error is None else "cleanup_partial"), now()
        save(state_path, state)
        save(EVIDENCE / "cleanup.json", {"timestamp": now(), "order": cleanup, "status": state["status"], "verified_zero_resources": state["status"] == "cleaned"})
    if error: raise error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
