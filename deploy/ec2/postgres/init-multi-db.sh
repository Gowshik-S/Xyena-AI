#!/bin/sh
set -eu

create_application_database() {
    role_name="$1"
    database_name="$2"
    role_password="$3"

    if ! psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --tuples-only \
        --command "SELECT 1 FROM pg_roles WHERE rolname = '$role_name'" | grep -q 1; then
        psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
            --set=role_password="$role_password" <<-EOSQL
			CREATE ROLE $role_name LOGIN PASSWORD :'role_password';
		EOSQL
    fi

    if ! psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --tuples-only \
        --command "SELECT 1 FROM pg_database WHERE datname = '$database_name'" | grep -q 1; then
        createdb --username "$POSTGRES_USER" --owner "$role_name" "$database_name"
    fi
}

if [ -n "${POSTGRES_HOST:-}" ]; then
    export PGHOST="$POSTGRES_HOST"
fi

psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --command "CREATE EXTENSION IF NOT EXISTS vector"

create_application_database bank_app bank_demo "$BANK_DB_PASSWORD"
create_application_database gst_app gst_demo "$GST_DB_PASSWORD"
create_application_database erp_app erp_demo "$ERP_DB_PASSWORD"
create_application_database registry_app registry_demo "$REGISTRY_DB_PASSWORD"
create_application_database funder_app funder_demo "$FUNDER_DB_PASSWORD"
create_application_database delivery_app delivery_demo "$DELIVERY_DB_PASSWORD"
create_application_database ledger_app ledger_demo "$LEDGER_DB_PASSWORD"
