#!/usr/bin/env bash
set -euo pipefail
name="${KEY_NAME:-eia-documentdb-$(date +%s)}"
file="${KEY_FILE:-/tmp/${name}.pem}"
case "${1:-create}" in
  create)
    umask 077
    aws ec2 create-key-pair --key-name "$name" --key-type rsa --query KeyMaterial --output text > "$file"
    chmod 600 "$file"
    printf 'export TF_VAR_key_name=%q\nexport DOCDB_KEY_FILE=%q\n' "$name" "$file"
    ;;
  delete)
    aws ec2 delete-key-pair --key-name "$name"
    rm -f "$file"
    ;;
  *) echo "usage: $0 create|delete" >&2; exit 2 ;;
esac
