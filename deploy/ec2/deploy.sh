#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$ROOT"

if [ ! -f .env ]; then
    python3 deploy/ec2/generate_env.py
fi

export COMPOSE_PARALLEL_LIMIT=1
COMPOSE="docker compose --env-file .env -f compose.ec2.yaml"

$COMPOSE config --quiet
$COMPOSE pull postgres redis minio minio-init
$COMPOSE build
$COMPOSE up -d --remove-orphans

for service in register-bank register-gst register-erp register-registry register-funder register-delivery register-ledger; do
    $COMPOSE --profile registration run --rm "$service"
done

deploy/ec2/smoke.sh
