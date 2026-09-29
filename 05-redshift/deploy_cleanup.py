#!/usr/bin/env python3
"""Ephemeral Redshift Serverless Point 5 run with incremental state and cleanup."""
from __future__ import annotations
import argparse, json, os, secrets, string, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
REGION = "us-east-2"
TAGS = [{"key":"Project","value":"EIA-AWS-Activity"},{"key":"Environment","value":"Lab"},{"key":"ManagedBy","value":"OMP"},{"key":"Point","value":"5"}]

def now(): return datetime.now(timezone.utc).isoformat()
def save(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")
def poll(fn, ok, timeout=900):
    end=time.time()+timeout
    while time.time()<end:
        x=fn()
        if ok(x): return x
        time.sleep(5)
    raise TimeoutError("AWS operation timed out")
def password():
    chars=string.ascii_letters+string.digits+"!#$%^*-_="
    return "".join(secrets.choice(chars) for _ in range(32))
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--execute", action="store_true")
    p.add_argument("--region", default=REGION)
    p.add_argument("--state", default=str(EVIDENCE/"state.json"))
    a=p.parse_args()
    state_path=Path(a.state)
    state={"started_at":now(),"region":a.region,"status":"started","resources":{}}
    save(EVIDENCE/"preflight.json", {"timestamp":now(),"region":a.region,"requested_base_capacity_rpu":4,"api_checks":["redshift-serverless.list_namespaces","redshift-serverless.list_workgroups","redshift-data.execute_statement","secretsmanager.get_secret_value","s3.upload_file","iam.create_role"],"execute":a.execute})
    if not a.execute:
        print("DRY-RUN: no AWS mutation"); return 0
    import boto3
    session=boto3.Session(region_name=a.region)
    rs=session.client("redshift-serverless"); data=session.client("redshift-data"); s3=session.client("s3"); sm=session.client("secretsmanager"); iam=session.client("iam")
    ident=session.client("sts").get_caller_identity()
    acct=ident["Account"]
    suffix=str(int(time.time()))[-8:]+secrets.token_hex(2)
    bucket=f"eia-p5-{acct}-{suffix}".lower(); ns=f"eia-p5-ns-{suffix}"; wg=f"eia-p5-wg-{suffix}"; role=f"EIA-P5-Copy-{suffix}"; secret_name=f"eia-p5-admin-{suffix}"
    state["account_id"]=acct; state["resources"]={"bucket":bucket,"namespace":ns,"workgroup":wg,"role":role,"secret_name":secret_name}; save(state_path,state)
    try:
        rs.list_namespaces(maxResults=1); rs.list_workgroups(maxResults=1)
        state["preflight_api_verified"]=True; save(state_path,state)
        s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint":a.region})
        s3.put_public_access_block(Bucket=bucket,PublicAccessBlockConfiguration={"BlockPublicAcls":True,"IgnorePublicAcls":True,"BlockPublicPolicy":True,"RestrictPublicBuckets":True})
        s3.put_bucket_encryption(Bucket=bucket,ServerSideEncryptionConfiguration={"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]})
        s3.put_bucket_tagging(Bucket=bucket,Tagging={"TagSet":[{"Key":x["key"],"Value":x["value"]} for x in TAGS]})
        state["resources"]["bucket_created"]=True; save(state_path,state)
        trust=json.loads((ROOT/"redshift-copy-role-trust.json").read_text())
        policy=json.loads((ROOT/"redshift-copy-role-policy.json").read_text().replace("REPLACE_BUCKET",bucket))
        iam.create_role(RoleName=role,AssumeRolePolicyDocument=json.dumps(trust),Description="Ephemeral Point 5 COPY role",Tags=[{"Key":x["key"],"Value":x["value"]} for x in TAGS])
        iam.put_role_policy(RoleName=role,PolicyName="Point5S3Read",PolicyDocument=json.dumps(policy))
        time.sleep(60)
        role_arn=f"arn:aws:iam::{acct}:role/{role}"; state["resources"]["role_arn"]=role_arn; state["resources"]["role_created"]=True; save(state_path,state)
        # Password exists only in process memory and is never persisted or printed.
        secret=sm.create_secret(Name=secret_name,Description="Ephemeral Point 5 Redshift admin",SecretString=json.dumps({"username":"admin","password":password()}),Tags=[{"Key":x["key"],"Value":x["value"]} for x in TAGS])
        secret_arn=secret["ARN"]; state["resources"]["secret_arn"]=secret_arn; state["resources"]["secret_created"]=True; save(state_path,state)
        ns_resp=rs.create_namespace(namespaceName=ns,adminUsername="admin",adminUserPassword=json.loads(sm.get_secret_value(SecretId=secret_arn)["SecretString"])["password"],dbName="dev",tags=TAGS)
        state["resources"]["namespace_arn"]=ns_resp.get("namespace")["namespaceArn"]; state["resources"]["namespace_created"]=True; save(state_path,state)
        poll(lambda:rs.get_namespace(namespaceName=ns),lambda x:x["namespace"]["status"] in {"AVAILABLE","FAILED"},1800)
        if rs.get_namespace(namespaceName=ns)["namespace"]["status"]!="AVAILABLE": raise RuntimeError("namespace failed")
        wg_resp=rs.create_workgroup(workgroupName=wg,namespaceName=ns,baseCapacity=4,publiclyAccessible=True,tags=TAGS)
        state["resources"]["workgroup_arn"]=wg_resp.get("workgroup")["workgroupArn"]; state["resources"]["workgroup_created"]=True; state["base_capacity_rpu"]=4; save(state_path,state)
        poll(lambda:rs.get_workgroup(workgroupName=wg),lambda x:x["workgroup"]["status"] in {"AVAILABLE","FAILED"},1800)
        if rs.get_workgroup(workgroupName=wg)["workgroup"]["status"]!="AVAILABLE": raise RuntimeError("workgroup failed")
        rs.update_namespace(namespaceName=ns,iamRoles=[role_arn])
        poll(lambda:rs.get_namespace(namespaceName=ns),lambda x:x["namespace"]["status"] in {"AVAILABLE","FAILED"},1800)
        if rs.get_namespace(namespaceName=ns)["namespace"]["status"]!="AVAILABLE": raise RuntimeError("namespace role association failed")
        state["infrastructure_ready_at"]=now(); save(EVIDENCE/"infrastructure.json",{"timestamp":now(),"region":a.region,"base_capacity_rpu":4,"resources":{k:v for k,v in state["resources"].items() if k.endswith("_arn") or k in ("bucket","namespace","workgroup")},"api_verified":True})
        env=os.environ | {"AWS_REGION":a.region,"REDSHIFT_S3_BUCKET":bucket,"REDSHIFT_S3_PREFIX":"punto5/input","REDSHIFT_WORKGROUP":wg,"REDSHIFT_DATABASE":"dev","REDSHIFT_SECRET_ARN":secret_arn,"REDSHIFT_COPY_ROLE_ARN":role_arn}
        import subprocess,sys
        run=subprocess.run([sys.executable,str(ROOT/"redshift_workload.py"),"--execute"],cwd=ROOT,env=env,text=True,capture_output=True)
        (EVIDENCE/"workload.log").write_text(run.stdout,encoding="utf-8")
        if run.returncode: raise RuntimeError("workload failed; see evidence/workload.log")
        state["workload_succeeded"]=True; save(state_path,state)
        # Preserve only the workload's sanitized stdout (it never contains SecretString).
        save(EVIDENCE/"workload.json",{"timestamp":now(),"returncode":run.returncode,"stdout":run.stdout})
    finally:
        state["cleanup_started_at"]=now(); save(state_path,state)
        cleanup=[]
        try:
            if state["resources"].get("workgroup_created"):
                rs.delete_workgroup(workgroupName=wg)
                def gone_workgroup():
                    try: return rs.get_workgroup(workgroupName=wg)
                    except rs.exceptions.ResourceNotFoundException: return {"gone": True}
                poll(gone_workgroup, lambda x:x.get("gone", False), 900)
                cleanup.append("workgroup")
        except Exception as e: cleanup.append("workgroup_error:"+type(e).__name__)
        try:
            if state["resources"].get("namespace_created"):
                rs.delete_namespace(namespaceName=ns)
                def gone_namespace():
                    try: return rs.get_namespace(namespaceName=ns)
                    except rs.exceptions.ResourceNotFoundException: return {"gone": True}
                poll(gone_namespace, lambda x:x.get("gone", False), 900)
                cleanup.append("namespace")
        except Exception as e: cleanup.append("namespace_error:"+type(e).__name__)
        try:
            if state["resources"].get("bucket_created"):
                objs=s3.list_objects_v2(Bucket=bucket).get("Contents",[])
                if objs: s3.delete_objects(Bucket=bucket,Delete={"Objects":[{"Key":o["Key"]} for o in objs]})
                s3.delete_bucket(Bucket=bucket); cleanup.append("bucket")
        except Exception as e: cleanup.append("bucket_error:"+type(e).__name__)
        try:
            if state["resources"].get("secret_created"): sm.delete_secret(SecretId=secret_arn,ForceDeleteWithoutRecovery=True); cleanup.append("secret")
        except Exception as e: cleanup.append("secret_error:"+type(e).__name__)
        try:
            if state["resources"].get("role_created"): iam.delete_role_policy(RoleName=role,PolicyName="Point5S3Read"); iam.delete_role(RoleName=role); cleanup.append("role")
        except Exception as e: cleanup.append("role_error:"+type(e).__name__)
        state["cleanup"]=cleanup; state["status"]="cleaned" if all("_error:" not in x for x in cleanup) else "cleanup_partial"; state["finished_at"]=now(); save(state_path,state)
        save(EVIDENCE/"cleanup.json",{"timestamp":now(),"order":cleanup,"status":state["status"],"verified_zero_resources":state["status"]=="cleaned"})
    return 0
if __name__ == "__main__": raise SystemExit(main())
