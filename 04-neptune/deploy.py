#!/usr/bin/env python3
"""Create temporary Point 4 Neptune resources with incremental rollback state."""
from __future__ import annotations
import argparse
import json
import os
import time
from pathlib import Path


REGION = os.getenv("AWS_REGION", "us-east-2")
CIDR = "201.221.176.28/32"
ENGINE = "1.4.8.0"
CLASS = "db.t3.medium"
TAGS = [{"Key": k, "Value": v} for k, v in {
    "Project": "EIA-AWS-Activity", "Environment": "Lab", "ManagedBy": "OMP", "Point": "4"
}.items()]
ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
STATE = EVIDENCE / "deployment-state.json"


def save(name: str, value: object) -> None:
    EVIDENCE.mkdir(exist_ok=True)
    (EVIDENCE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def save_state(state: dict) -> None:
    EVIDENCE.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def route_table_for_subnet(subnet: dict, route_tables: list[dict], vpc_id: str) -> dict | None:
    explicit = {a["SubnetId"]: a["RouteTableId"] for rt in route_tables for a in rt.get("Associations", []) if not a.get("Main") and a.get("SubnetId")}
    table_id = explicit.get(subnet["SubnetId"])
    if table_id:
        return next((rt for rt in route_tables if rt["RouteTableId"] == table_id), None)
    return next((rt for rt in route_tables if any(a.get("Main") and a.get("VpcId") == vpc_id for a in rt.get("Associations", []))), None)


def reconcile_security_group(state: dict, ec2) -> str | None:
    """Recover a created SG when the state write was interrupted."""
    if state.get("sg"):
        return state["sg"]
    name = state.get("sg_name")
    vpc = state.get("vpc")
    if not name or not vpc:
        return None
    groups = ec2.describe_security_groups(
        Filters=[{"Name": "group-name", "Values": [name]}, {"Name": "vpc-id", "Values": [vpc]}]
    ).get("SecurityGroups", [])
    if len(groups) != 1:
        return None
    state["sg"] = groups[0]["GroupId"]
    save_state(state)
    return state["sg"]


def rollback(state: dict, rds, ec2) -> None:
    """Best effort rollback; never changes pre-existing network resources."""
    instance = state.get("instance")
    cluster = state.get("cluster")
    if instance:
        try:
            rds.delete_db_instance(DBInstanceIdentifier=instance, SkipFinalSnapshot=True, DeleteAutomatedBackups=True)
            rds.get_waiter("db_instance_deleted").wait(DBInstanceIdentifier=instance, WaiterConfig={"Delay": 5, "MaxAttempts": 12})
        except Exception:
            pass
    if cluster:
        try:
            rds.delete_db_cluster(DBClusterIdentifier=cluster, SkipFinalSnapshot=True)
            rds.get_waiter("db_cluster_deleted").wait(DBClusterIdentifier=cluster, WaiterConfig={"Delay": 5, "MaxAttempts": 12})
        except Exception:
            pass
    if state.get("subnet_group"):
        try:
            rds.delete_db_subnet_group(DBSubnetGroupName=state["subnet_group"])
        except Exception:
            pass
    sg = reconcile_security_group(state, ec2)
    if sg:
        try:
            ec2.delete_security_group(GroupId=sg)
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="print the plan without contacting AWS or mutating resources")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({"dry_run": True, "region": REGION, "actions": ["verify orderability and subnet routes", "create temporary SG/subnet group/Neptune resources", "write incremental state", "rollback on failure"], "mutations": []}))
        return 0
    import boto3

    ec2 = boto3.client("ec2", region_name=REGION)
    rds = boto3.client("rds", region_name=REGION)
    sts = boto3.client("sts", region_name=REGION)
    state: dict = {"region": REGION, "status": "starting", "resources": {}}
    try:
        ident = sts.get_caller_identity()
        save("cost-before.json", {"region": REGION, "note": "No cost API estimate; Neptune resources absent before run", "caller": ident["Arn"]})
        options = rds.describe_orderable_db_instance_options(Engine="neptune", EngineVersion=ENGINE, DBInstanceClass=CLASS, MaxRecords=100)["OrderableDBInstanceOptions"]
        if not options:
            raise RuntimeError("Requested Neptune engine/class is not orderable in this region")
        vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
        if len(vpcs) != 1:
            raise RuntimeError(f"Expected exactly one default VPC, found {len(vpcs)}")
        vpc = vpcs[0]
        subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc["VpcId"]]}, {"Name": "default-for-az", "Values": ["true"]}])["Subnets"]
        by_az = {}
        for subnet in subnets:
            by_az.setdefault(subnet["AvailabilityZone"], subnet)
        if len(by_az) < 2:
            raise RuntimeError("Default VPC has fewer than two default subnets/AZs")
        chosen = list(by_az.values())[:2]
        routes = ec2.describe_route_tables(Filters=[{"Name": "vpc-id", "Values": [vpc["VpcId"]]}])["RouteTables"]
        gateways = ec2.describe_internet_gateways()["InternetGateways"]
        attached = {g["InternetGatewayId"] for g in gateways if any(a.get("VpcId") == vpc["VpcId"] for a in g.get("Attachments", []))}
        for subnet in chosen:
            table = route_table_for_subnet(subnet, routes, vpc["VpcId"])
            valid = table and any(r.get("DestinationCidrBlock") == "0.0.0.0/0" and r.get("GatewayId") in attached for r in table.get("Routes", []))
            if not valid:
                raise RuntimeError(f"Subnet {subnet['SubnetId']} has no existing 0.0.0.0/0 route to an IGW; refusing network changes")
        igw_ids = [g for g in attached]
        if not igw_ids:
            raise RuntimeError("Default VPC has no attached internet gateway; refusing to create or attach one")
        suffix = str(int(time.time()))
        cluster, instance = f"eia-p4-{suffix}", f"eia-p4-writer-{suffix}"
        sg_name, subnet_group = f"eia-p4-sg-{suffix}", f"eia-p4-subnets-{suffix}"
        state.update({"vpc": vpc["VpcId"], "cluster": cluster, "instance": instance, "sg": None, "sg_name": sg_name, "subnet_group": subnet_group, "status": "planned", "igw": igw_ids[0], "igw_attached_by_run": False, "igw_created_by_run": False})
        save_state(state)
        sgid = ec2.create_security_group(GroupName=sg_name, Description="Temporary Neptune Point 4 lab", VpcId=vpc["VpcId"], TagSpecifications=[{"ResourceType": "security-group", "Tags": TAGS}])["GroupId"]
        state.update(sg=sgid, status="security_group_created")
        save_state(state)
        ec2.authorize_security_group_ingress(GroupId=sgid, IpPermissions=[{"IpProtocol": "tcp", "FromPort": 8182, "ToPort": 8182, "IpRanges": [{"CidrIp": CIDR, "Description": "Temporary lab client /32"}]}])
        rds.create_db_subnet_group(DBSubnetGroupName=subnet_group, DBSubnetGroupDescription="Temporary Point 4 Neptune subnets", SubnetIds=[s["SubnetId"] for s in chosen], Tags=TAGS)
        state["status"] = "subnet_group_created"
        save_state(state)
        rds.create_db_cluster(DBClusterIdentifier=cluster, Engine="neptune", EngineVersion=ENGINE, StorageEncrypted=True, EnableIAMDatabaseAuthentication=True, DBSubnetGroupName=subnet_group, VpcSecurityGroupIds=[sgid], Tags=TAGS)
        state["status"] = "cluster_created"
        save_state(state)
        rds.create_db_instance(DBInstanceIdentifier=instance, DBInstanceClass=CLASS, Engine="neptune", DBClusterIdentifier=cluster, PubliclyAccessible=True, Tags=TAGS)
        state["status"] = "instance_created"
        save_state(state)
        rds.get_waiter("db_instance_available").wait(DBInstanceIdentifier=instance, WaiterConfig={"Delay": 30, "MaxAttempts": 60})
        rds.get_waiter("db_cluster_available").wait(DBClusterIdentifier=cluster, WaiterConfig={"Delay": 30, "MaxAttempts": 60})
        desc = rds.describe_db_clusters(DBClusterIdentifier=cluster)["DBClusters"][0]
        inst = rds.describe_db_instances(DBInstanceIdentifier=instance)["DBInstances"][0]
        state.update({"resource_id": desc["DbClusterResourceId"], "status": "ready", "iam_policy": "iam-policy.json (reference only; no inline policy attached)"})
        save_state(state)
        save("preflight.json", {"region": REGION, "engine": "neptune", "engine_version": ENGINE, "db_instance_class": CLASS, "orderable": True, "default_vpc_id": vpc["VpcId"], "subnets": [{"id": s["SubnetId"], "az": s["AvailabilityZone"]} for s in chosen], "public_endpoint": True, "iam_db_auth": True, "tls": True, "internet_gateway_id": igw_ids[0], "internet_gateway_attached_by_run": False, "ingress_cidr": CIDR, "tags": TAGS})
        save("infrastructure.json", {"region": REGION, "cluster_identifier": cluster, "instance_identifier": instance, "instance_class": CLASS, "engine_version": desc.get("EngineVersion"), "cluster_status": desc.get("Status"), "instance_status": inst.get("DBInstanceStatus"), "publicly_accessible": inst.get("PubliclyAccessible"), "iam_auth": desc.get("IAMDatabaseAuthenticationEnabled"), "storage_encrypted": desc.get("StorageEncrypted"), "security_group_id": sgid, "subnet_group": subnet_group, "endpoint": "[REDACTED]", "tags": TAGS})
        print(json.dumps({"ok": True, "cluster": cluster, "instance": instance, "endpoint": "[REDACTED]", "state": str(STATE)}))
        return 0
    except Exception:
        if state.get("status") != "starting":
            rollback(state, rds, ec2)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
