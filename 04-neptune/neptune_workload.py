#!/usr/bin/env python3
"""Neptune openCypher workload; dry-run is the safe default (no AWS calls)."""
from __future__ import annotations

import argparse
import json
import os
from typing import Any

VERTICES = [
    {"id": "ana", "kind": "Person", "name": "Ana"},
    {"id": "bruno", "kind": "Person", "name": "Bruno"},
    {"id": "carla", "kind": "Person", "name": "Carla"},
    {"id": "diego", "kind": "Person", "name": "Diego"},
    {"id": "eia", "kind": "Course", "name": "Ingenieria de Datos"},
    {"id": "cloud", "kind": "Course", "name": "Cloud AWS"},
    {"id": "python", "kind": "Skill", "name": "Python"},
    {"id": "graph", "kind": "Skill", "name": "Graph"},
    {"id": "aws", "kind": "Skill", "name": "AWS"},
    {"id": "team", "kind": "Team", "name": "Equipo A"},
]
EDGES = [
    ("ana", "ENROLLED_IN", "eia"), ("bruno", "ENROLLED_IN", "eia"),
    ("carla", "ENROLLED_IN", "cloud"), ("diego", "ENROLLED_IN", "cloud"),
    ("ana", "KNOWS", "python"), ("ana", "KNOWS", "aws"),
    ("bruno", "KNOWS", "python"), ("bruno", "KNOWS", "graph"),
    ("carla", "KNOWS", "aws"), ("carla", "KNOWS", "graph"),
    ("diego", "KNOWS", "python"), ("diego", "KNOWS", "aws"),
    ("ana", "MEMBER_OF", "team"), ("bruno", "MEMBER_OF", "team"),
    ("carla", "MEMBER_OF", "team"),
]

# Three intentionally different traversals used in the report.
TRAVERSALS = {
    "people_and_courses": "MATCH (p:Person)-[:ENROLLED_IN]->(c:Course) RETURN p.id AS person, c.id AS course ORDER BY person",
    "skill_reachability": "MATCH (p:Person)-[:KNOWS]->(s:Skill) RETURN p.id AS person, collect(s.id) AS skills ORDER BY person",
    "team_to_course": "MATCH (p:Person)-[:MEMBER_OF]->(:Team), (p)-[:ENROLLED_IN]->(c:Course) RETURN p.id AS person, c.id AS course ORDER BY person",
}


def queries() -> list[str]:
    vertex_queries = [
        "CREATE (n:%s {id: '%s', name: '%s'})" % (v["kind"], v["id"], v["name"])
        for v in VERTICES
    ]
    edge_queries = [
        "MATCH (a {id: '%s'}), (b {id: '%s'}) CREATE (a)-[:%s]->(b)" % (a, b, label)
        for a, label, b in EDGES
    ]
    return vertex_queries + edge_queries


def sanitize(value: Any) -> Any:
    """Keep result evidence useful while never printing connection/secret fields."""
    if isinstance(value, dict):
        blocked = {"password", "secret", "authorization", "endpoint", "host", "uri"}
        return {k: "[REDACTED]" if k.lower() in blocked else sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="execute against Neptune; otherwise no AWS calls")
    parser.add_argument("--endpoint", default=os.getenv("NEPTUNE_ENDPOINT"))
    parser.add_argument("--port", type=int, default=int(os.getenv("NEPTUNE_PORT", "8182")))
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-2"))
    args = parser.parse_args()
    if args.execute and not args.endpoint:
        parser.error("--execute requires --endpoint or NEPTUNE_ENDPOINT")

    report: dict[str, Any] = {
        "mode": "execute" if args.execute else "dry-run",
        "vertices": len(VERTICES), "edges": len(EDGES),
        "minimums_met": len(VERTICES) >= 10 and len(EDGES) >= 15,
        "traversals": list(TRAVERSALS),
    }
    if not args.execute:
        report["planned_mutations"] = len(queries())
        report["sanitized_results"] = {name: "not executed (dry-run)" for name in TRAVERSALS}
    else:
        import boto3
        client = boto3.client("neptunedata", region_name=args.region,
                              endpoint_url=f"https://{args.endpoint}:{args.port}")
        for query in queries():
            client.execute_open_cypher_query(openCypherQuery=query)
        results = {}
        for name, query in TRAVERSALS.items():
            response = client.execute_open_cypher_query(openCypherQuery=query)
            results[name] = sanitize(response.get("results", []))
        report["sanitized_results"] = results
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
