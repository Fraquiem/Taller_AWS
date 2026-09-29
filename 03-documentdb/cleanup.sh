#!/usr/bin/env bash
set -euo pipefail
terraform destroy -auto-approve
if [[ -n "${KEY_NAME:-}" ]]; then
  aws ec2 delete-key-pair --key-name "$KEY_NAME" --region "${AWS_REGION:-us-east-2}" || true
fi
rm -f "${DOCDB_KEY_FILE:-/tmp/${KEY_NAME:-eia-documentdb-unused}.pem}"
# Secret deletion is normally handled by Terraform; this optional command removes the recovery window.
if [[ "${FORCE_DELETE_SECRET:-0}" == "1" && -n "${SECRET_ARN:-}" ]]; then
  aws secretsmanager delete-secret --secret-id "$SECRET_ARN" --force-delete-without-recovery --region "${AWS_REGION:-us-east-2}"
fi
