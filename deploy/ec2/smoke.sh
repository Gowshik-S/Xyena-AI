#!/bin/sh
set -eu

check_json_health() {
    label="$1"
    url="$2"
    attempts=0
    until curl --fail --silent --show-error --max-time 5 "$url" >/dev/null; do
        attempts=$((attempts + 1))
        if [ "$attempts" -ge 60 ]; then
            echo "$label did not become healthy: $url" >&2
            exit 1
        fi
        sleep 5
    done
    echo "healthy: $label"
}

check_page() {
    label="$1"
    url="$2"
    curl --fail --silent --show-error --max-time 10 "$url" >/dev/null
    echo "reachable: $label"
}

check_json_health "Xyena API" "http://127.0.0.1:8080/health/ready"
check_json_health "MCP control plane" "http://127.0.0.1:8081/health/ready"
check_json_health "Guardian" "http://127.0.0.1:8082/health/ready"
check_json_health "Bank" "http://127.0.0.1:8090/health/ready"
check_json_health "GST" "http://127.0.0.1:8091/health/ready"
check_json_health "Buyer ERP" "http://127.0.0.1:8092/health/ready"
check_json_health "Business Registry" "http://127.0.0.1:8093/health/ready"
check_json_health "Funder Marketplace" "http://127.0.0.1:8094/health/ready"
check_json_health "Delivery" "http://127.0.0.1:8095/health/ready"
check_json_health "Ledger and Payment" "http://127.0.0.1:8096/health/ready"
check_page "Xyena web" "http://127.0.0.1:4173/"

echo "All local origins are healthy."
