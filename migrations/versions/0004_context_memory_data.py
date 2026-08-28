"""Scoped context snapshots, Agents SDK sessions, durable memory, and data vault."""

import hashlib
from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0004_context_memory_data"
down_revision: str | None = "0003_guardian"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_TYPE = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _base_columns(*, tenant: bool = True, version: bool = False) -> list[sa.Column]:
    columns: list[sa.Column] = [sa.Column("id", UUID_TYPE, primary_key=True)]
    if tenant:
        columns.append(sa.Column("tenant_id", UUID_TYPE, nullable=False, index=True))
    if version:
        columns.append(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    columns.extend(
        [
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        ]
    )
    return columns


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    for schema in ("memory", "data_vault"):
        op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    op.add_column(
        "runs",
        sa.Column("runtime_scope", JSONB, nullable=False, server_default="{}"),
        schema="agent",
    )

    op.create_table(
        "session_items",
        *_base_columns(),
        sa.Column("session_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("conversation_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("item", JSONB, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["session_id"], ["conversation.sessions.id"]),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.conversations.id"]),
        sa.UniqueConstraint("tenant_id", "session_id", "sequence"),
        schema="memory",
    )
    op.create_table(
        "records",
        *_base_columns(version=True),
        sa.Column("organization_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("user_id", UUID_TYPE, index=True),
        sa.Column("kind", sa.String(50), nullable=False, index=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("structured_content", JSONB, nullable=False, server_default="{}"),
        sa.Column("embedding", Vector(1536)),
        sa.Column("sensitivity", sa.String(30), nullable=False, server_default="INTERNAL"),
        sa.Column("source_type", sa.String(100), nullable=False),
        sa.Column("source_id", UUID_TYPE),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE", index=True),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        schema="memory",
    )
    op.create_table(
        "evidence",
        *_base_columns(),
        sa.Column("memory_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("source_type", sa.String(100), nullable=False),
        sa.Column("source_ref", sa.String(1000), nullable=False),
        sa.Column("evidence_hash", sa.String(128), nullable=False),
        sa.ForeignKeyConstraint(["memory_id"], ["memory.records.id"]),
        schema="memory",
    )
    op.create_table(
        "context_snapshots",
        *_base_columns(),
        sa.Column("run_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("token_budget", sa.Integer(), nullable=False),
        sa.Column("estimated_tokens", sa.Integer(), nullable=False),
        sa.Column("policy_bundle_version", sa.String(100), nullable=False),
        sa.Column("snapshot_hash", sa.String(128), nullable=False),
        sa.Column("items", JSONB, nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent.runs.id"]),
        sa.UniqueConstraint("tenant_id", "run_id", "turn_number"),
        schema="memory",
    )

    op.create_table(
        "objects",
        *_base_columns(version=True),
        sa.Column("organization_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("owner_user_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("object_key", sa.String(1000), nullable=False),
        sa.Column("display_name", sa.String(300), nullable=False),
        sa.Column("media_type", sa.String(200), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False, index=True),
        sa.Column("classification", sa.String(30), nullable=False),
        sa.Column("schema_name", sa.String(200)),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("encryption_key_ref", sa.String(500)),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE", index=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "object_key"),
        schema="data_vault",
    )
    op.create_table(
        "grants",
        *_base_columns(version=True),
        sa.Column("data_object_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("grantor_user_id", UUID_TYPE, nullable=False),
        sa.Column("grantee_type", sa.String(30), nullable=False),
        sa.Column("grantee_id", sa.String(200), nullable=False, index=True),
        sa.Column("purposes", postgresql.ARRAY(sa.String(200)), nullable=False, server_default="{}"),
        sa.Column("permissions", postgresql.ARRAY(sa.String(50)), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["data_object_id"], ["data_vault.objects.id"]),
        schema="data_vault",
    )
    op.create_table(
        "access_events",
        *_base_columns(),
        sa.Column("data_object_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("actor_type", sa.String(30), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("purpose", sa.String(500), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("correlation_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("outcome", sa.String(30), nullable=False),
        sa.ForeignKeyConstraint(["data_object_id"], ["data_vault.objects.id"]),
        schema="data_vault",
    )
    op.execute(
        sa.text(
            "CREATE INDEX ix_memory_records_embedding_hnsw ON memory.records "
            "USING hnsw (embedding vector_cosine_ops)"
        )
    )
    _enable_rls()
    _seed_agent_catalog()


def _enable_rls() -> None:
    scoped = {
        "memory": ["session_items", "records", "evidence", "context_snapshots"],
        "data_vault": ["objects", "grants", "access_events"],
    }
    for schema, tables in scoped.items():
        for table in tables:
            qualified = f'"{schema}"."{table}"'
            policy = f"tenant_isolation_{schema}_{table}"
            op.execute(sa.text(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY"))
            op.execute(sa.text(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY"))
            op.execute(
                sa.text(
                    f"CREATE POLICY {policy} ON {qualified} USING ("
                    "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
                    "OR current_setting('app.service_role', true) IN ('worker', 'mcp', 'guardian')) "
                    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
                    "OR current_setting('app.service_role', true) IN ('worker', 'mcp', 'guardian'))"
                )
            )


def _seed_agent_catalog() -> None:
    definitions = [
        ("30000000-0000-4000-8000-000000000001", "xyena-supervisor", "Xyena Supervisor", "Own the user-facing answer and delegate bounded analysis.", "ACTIVE"),
        ("30000000-0000-4000-8000-000000000002", "intake-agent", "Intake Agent", "Clarify goals and produce structured intake without taking actions.", "ACTIVE"),
        ("30000000-0000-4000-8000-000000000003", "business-agent", "Business Agent", "Perform domain-neutral business analysis from supplied evidence.", "ACTIVE"),
        ("30000000-0000-4000-8000-000000000004", "invoice-agent", "Invoice Agent", "Catalog placeholder; domain behavior and tools are not installed.", "DISABLED"),
        ("30000000-0000-4000-8000-000000000005", "delivery-agent", "Delivery Agent", "Catalog placeholder; domain behavior and tools are not installed.", "DISABLED"),
        ("30000000-0000-4000-8000-000000000006", "payment-agent", "Payment Agent", "Catalog placeholder; financial execution is not installed.", "DISABLED"),
        ("30000000-0000-4000-8000-000000000007", "fraud-risk-agent", "Fraud/Risk Agent", "Review evidence for risk signals without authorizing execution.", "ACTIVE"),
        ("30000000-0000-4000-8000-000000000008", "credit-agent", "Credit Agent", "Catalog placeholder; lending behavior and tools are not installed.", "DISABLED"),
        ("30000000-0000-4000-8000-000000000009", "decision-orchestrator", "Decision Orchestrator", "Catalog placeholder; domain decision workflows are not installed.", "DISABLED"),
        ("30000000-0000-4000-8000-000000000010", "funding-agent", "Funding Agent", "Catalog placeholder; funding behavior and tools are not installed.", "DISABLED"),
        ("30000000-0000-4000-8000-000000000011", "guardian-agent", "Guardian Agent", "Explain Guardian decisions; deterministic Guardian service remains authoritative.", "ACTIVE"),
        ("30000000-0000-4000-8000-000000000012", "monitoring-agent", "Monitoring Agent", "Summarize platform signals without changing state.", "ACTIVE"),
    ]
    definition_table = sa.table(
        "definitions",
        sa.column("id", UUID_TYPE),
        sa.column("stable_name", sa.String()),
        sa.column("display_name", sa.String()),
        sa.column("purpose", sa.Text()),
        sa.column("owner", sa.String()),
        sa.column("status", sa.String()),
        schema="agent",
    )
    version_table = sa.table(
        "versions",
        sa.column("id", UUID_TYPE),
        sa.column("definition_id", UUID_TYPE),
        sa.column("version", sa.String()),
        sa.column("instructions_ref", sa.String()),
        sa.column("instructions_hash", sa.String()),
        sa.column("model_policy", JSONB),
        sa.column("output_schema", JSONB),
        sa.column("context_profile", JSONB),
        sa.column("budgets", JSONB),
        sa.column("status", sa.String()),
        schema="agent",
    )
    op.bulk_insert(
        definition_table,
        [
            {
                "id": UUID(item[0]),
                "stable_name": item[1],
                "display_name": item[2],
                "purpose": item[3],
                "owner": "platform",
                "status": item[4],
            }
            for item in definitions
        ],
    )
    active = [item for item in definitions if item[4] == "ACTIVE"]
    op.bulk_insert(
        version_table,
        [
            {
                "id": UUID(item[0].replace("30000000", "31000000")),
                "definition_id": UUID(item[0]),
                "version": "1.0.0",
                "instructions_ref": f"builtin://agents/{item[1]}/1.0.0",
                "instructions_hash": hashlib.sha256(item[3].encode()).hexdigest(),
                "model_policy": {"provider": "openai", "model_alias": "default"},
                "output_schema": {"type": "string"},
                "context_profile": {"memory": "scoped", "maximum_sensitivity": "CONFIDENTIAL"},
                "budgets": {"max_turns": 12, "max_tool_calls": 20, "context_tokens": 24000},
                "status": "ACTIVE",
            }
            for item in active
        ],
    )


def downgrade() -> None:
    seeded_ids = ",".join(
        f"'{value}'::uuid"
        for value in [
            "30000000-0000-4000-8000-000000000001",
            "30000000-0000-4000-8000-000000000002",
            "30000000-0000-4000-8000-000000000003",
            "30000000-0000-4000-8000-000000000004",
            "30000000-0000-4000-8000-000000000005",
            "30000000-0000-4000-8000-000000000006",
            "30000000-0000-4000-8000-000000000007",
            "30000000-0000-4000-8000-000000000008",
            "30000000-0000-4000-8000-000000000009",
            "30000000-0000-4000-8000-000000000010",
            "30000000-0000-4000-8000-000000000011",
            "30000000-0000-4000-8000-000000000012",
        ]
    )
    op.execute(sa.text(f"DELETE FROM agent.versions WHERE definition_id IN ({seeded_ids})"))
    op.execute(sa.text(f"DELETE FROM agent.definitions WHERE id IN ({seeded_ids})"))
    op.execute(sa.text('DROP SCHEMA IF EXISTS "data_vault" CASCADE'))
    op.execute(sa.text('DROP SCHEMA IF EXISTS "memory" CASCADE'))
    op.drop_column("runs", "runtime_scope", schema="agent")
