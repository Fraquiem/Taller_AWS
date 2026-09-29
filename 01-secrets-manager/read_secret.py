"""Read the current version of one Secrets Manager secret.

The secret identifier is supplied through SECRET_ID; no credential or secret value
is embedded in the source. The caller's AWS identity is resolved by the normal
Boto3 credential chain.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

import boto3


def read_current_secret(secret_id: str, region: str) -> dict[str, Any]:
    client = boto3.client("secretsmanager", region_name=region)
    response = client.get_secret_value(SecretId=secret_id)
    secret_string = response.get("SecretString")
    if secret_string is None:
        raise ValueError("The selected secret does not contain SecretString")
    value = json.loads(secret_string)
    if not isinstance(value, dict):
        raise ValueError("The secret value must be a JSON object")
    return value


if __name__ == "__main__":
    secret_id = os.environ["SECRET_ID"]
    region = os.environ.get("AWS_REGION", "us-east-2")
    value = read_current_secret(secret_id, region)
    # Deliberately print only non-sensitive metadata for reproducible evidence.
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    print(
        json.dumps(
            {
                "keys": sorted(value),
                "value_sha256": hashlib.sha256(canonical).hexdigest(),
                "version_stage": "AWSCURRENT",
            }
        )
    )
