#!/usr/bin/env python3
"""Destroy the temporary Point 4 Neptune run and verify real leftovers."""
from __future__ import annotations
import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "evidence" / "deployment-state.json"
CLEANUP = ROOT / "evidence" / "cleanup.json"


def wait_instance_gone(rds, identifier: str) -> bool:
    """Wait through waiter timeout, then keep polling before allowing cluster deletion."""
    try:
        rds.get_waiter("db_instance_deleted").wait(
            DBInstanceIdentifier=identifier, WaiterConfig={"Delay": 20, "MaxAttempts": 60}
        )
        return True
    except Exception:
        # A waiter timeout is not proof that the instance still exists. Reconcile
        # with the API before deciding whether cluster deletion is safe.
        for _ in range(60):
            try:
                instances = rds.describe_db_instances(DBInstanceIdentifier=identifier).get("DBInstances", [])
                if not instances:
                    return True
            except rds.exceptions.DBInstanceNotFoundFault:
                return True
            time.sleep(20)
        return False


def reconcile_security_group(state: dict, ec2) -> str | None:
    if state.get("sg"):
        return state["sg"]
    if not state.get("sg_name") or not state.get("vpc"):
        return None
    groups = ec2.describe_security_groups(
        Filters=[{"Name": "group-name", "Values": [state["sg_name"]]}, {"Name": "vpc-id", "Values": [state["vpc"]]}]
    ).get("SecurityGroups", [])
    return groups[0]["GroupId"] if len(groups) == 1 else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="print cleanup plan without contacting AWS or deleting resources")
    args = parser.parse_args()
    if args.dry_run:
        print(json.dumps({"dry_run": True, "actions": ["delete instance, cluster, subnet group and security group", "verify subnet groups and network interfaces"], "mutations": []}))
        return 0

    import boto3
    state = json.loads(STATE.read_text())
    region = state["region"]
    rds = boto3.client("rds", region_name=region)
    ec2 = boto3.client("ec2", region_name=region)
    errors: list[str] = []
    sg_id = reconcile_security_group(state, ec2)
    instance_gone = not state.get("instance")

    try:
        if state.get("instance"):
            try:
                rds.delete_db_instance(DBInstanceIdentifier=state["instance"], SkipFinalSnapshot=True, DeleteAutomatedBackups=True)
            except rds.exceptions.DBInstanceNotFoundFault:
                pass
            try:
                instance_gone = wait_instance_gone(rds, state["instance"])
            except Exception as exc:
                errors.append(f"instance wait: {exc}")
                instance_gone = False

        if state.get("cluster") and instance_gone:
            try:
                rds.delete_db_cluster(DBClusterIdentifier=state["cluster"], SkipFinalSnapshot=True)
            except rds.exceptions.DBClusterNotFoundFault:
                pass
            try:
                rds.get_waiter("db_cluster_deleted").wait(DBClusterIdentifier=state["cluster"], WaiterConfig={"Delay": 20, "MaxAttempts": 60})
            except Exception as exc:
                errors.append(f"cluster wait: {exc}")
        elif state.get("cluster"):
            errors.append("cluster deletion skipped: instance is not confirmed gone")

        if state.get("subnet_group"):
            try:
                rds.delete_db_subnet_group(DBSubnetGroupName=state["subnet_group"])
            except rds.exceptions.DBSubnetGroupNotFoundFault:
                pass
        if sg_id:
            try:
                ec2.delete_security_group(GroupId=sg_id)
            except ec2.exceptions.InvalidGroupNotFound:
                pass
    except Exception as exc:
        errors.append(f"cleanup operation: {exc}")

    # Keep historical evidence untouched; this is a fresh, count-based verification.
    try:
        clusters = rds.describe_db_clusters().get("DBClusters", [])
        instances = rds.describe_db_instances().get("DBInstances", [])
        subnet_groups = rds.describe_db_subnet_groups().get("DBSubnetGroups", [])
        tagged_sgs = ec2.describe_security_groups(Filters=[{"Name": "tag:Point", "Values": ["4"]}]).get("SecurityGroups", [])
        tagged_igws = ec2.describe_internet_gateways(Filters=[{"Name": "tag:Point", "Values": ["4"]}]).get("InternetGateways", [])
        eips = ec2.describe_addresses(Filters=[{"Name": "tag:Point", "Values": ["4"]}]).get("Addresses", [])
        nat_gateways = ec2.describe_nat_gateways(Filters=[{"Name": "tag:Point", "Values": ["4"]}]).get("NatGateways", [])
        eni_filters = [{"Name": "group-id", "Values": [sg_id]}] if sg_id else []
        enis = ec2.describe_network_interfaces(Filters=eni_filters).get("NetworkInterfaces", []) if eni_filters else []
        run_subnet_groups = [g for g in subnet_groups if g.get("DBSubnetGroupName") == state.get("subnet_group") or any(t.get("Key") == "Point" and t.get("Value") == "4" for t in g.get("Tags", []))]
        leftovers = {"neptune_clusters": clusters, "neptune_instances": instances, "db_subnet_groups": run_subnet_groups, "tagged_security_groups": tagged_sgs, "tagged_igws": tagged_igws, "eips": eips, "nat_gateways": nat_gateways, "network_interfaces_for_run_sg": enis}
        counts = {key: len(value) for key, value in leftovers.items()}
    except Exception as exc:
        errors.append(f"verification: {exc}")
        leftovers = {}
        counts = {}

    summary = {"region": region, "deleted": {"cluster": state.get("cluster"), "instance": state.get("instance"), "subnet_group": state.get("subnet_group"), "security_group": sg_id, "iam_policy": None}, "leftover_counts": counts, "cleanup_verified": not errors and bool(leftovers) and all(count == 0 for count in counts.values()), "errors": errors}
    CLEANUP.write_text(json.dumps(summary, indent=2) + "\n")
    if not summary["cleanup_verified"]:
        raise RuntimeError(f"Cleanup verification failed: {counts}; errors: {errors}")
    STATE.unlink(missing_ok=True)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
