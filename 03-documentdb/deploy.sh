#!/usr/bin/env bash
set -euo pipefail
: "${TF_VAR_docdb_password:?Set TF_VAR_docdb_password from a secure prompt or Secrets Manager; never commit it}"
: "${TF_VAR_trusted_cidr:?Set TF_VAR_trusted_cidr to your public /32}"
: "${TF_VAR_key_name:?Set TF_VAR_key_name to an existing EC2 key pair}"
terraform init
terraform validate
terraform plan -out=point3.tfplan
printf 'Review the plan, then run: terraform apply point3.tfplan\n'
