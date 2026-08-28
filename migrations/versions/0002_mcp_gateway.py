"""MCP registry, schema versions, policy grants, calls, attempts, and results."""

import hashlib
import json
from collections.abc import Sequence
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_mcp_gateway"
down_revision: str | None = "0001_core_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_TYPE = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())

CORE_SERVER_ID = UUID("10000000-0000-4000-8000-000000000001")
DESCRIBE_TOOL_ID = UUID("10000000-0000-4000-8000-000000000002")
DESCRIBE_VERSION_ID = UUID("10000000-0000-4000-8000-000000000003")
DESCRIBE_POLICY_ID = UUID("10000000-0000-4000-8000-000000000004")
RISK_TOOL_ID = UUID("10000000-0000-4000-8000-000000000005")
RISK_VERSION_ID = UUID("10000000-0000-4000-8000-000000000006")
RISK_POLICY_ID = UUID("10000000-0000-4000-8000-000000000007")


def _base_columns(*, tenant: bool = False, version: bool = False) -> list[sa.Column]:
    columns: list[sa.Column] = [sa.Column("id", UUID_TYPE, primary_key=True)]
    if tenant:
        columns.append(sa.Column("tenant_id", UUID_TYPE, nullable=False, index=True))
    if version:
        columns.append(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    columns.extend(
        [
            sa.Column(
                "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
            ),
        ]
    )
    return columns


def upgrade() -> None:
    op.execute(sa.text('CREATE SCHEMA IF NOT EXISTS "mcp"'))

    op.create_table(
        "servers",
        *_base_columns(version=True),
        sa.Column("tenant_id", UUID_TYPE, index=True),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("transport", sa.String(40), nullable=False),
        sa.Column("endpoint", sa.String(2000), nullable=False),
        sa.Column("auth_type", sa.String(50), nullable=False, server_default="BEARER"),
        sa.Column("secret_ref", sa.String(500)),
        sa.Column("trust_tier", sa.String(50), nullable=False, server_default="UNREVIEWED"),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column(
            "allowed_egress_hosts", postgresql.ARRAY(sa.String(255)), nullable=False, server_default="{}"
        ),
        sa.Column("timeout_seconds", sa.Numeric(8, 3), nullable=False, server_default="30"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("discovery_hash", sa.String(128)),
        sa.Column("last_discovered_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "label"),
        schema="mcp",
    )
    op.create_table(
        "server_versions",
        *_base_columns(),
        sa.Column("server_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("implementation_name", sa.String(200)),
        sa.Column("implementation_version", sa.String(100)),
        sa.Column("protocol_version", sa.String(100)),
        sa.Column("discovery_hash", sa.String(128), nullable=False),
        sa.Column("discovery_document", JSONB, nullable=False),
        sa.ForeignKeyConstraint(["server_id"], ["mcp.servers.id"]),
        sa.UniqueConstraint("server_id", "discovery_hash"),
        schema="mcp",
    )
    op.create_table(
        "tools",
        *_base_columns(version=True),
        sa.Column("server_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("canonical_name", sa.String(200), nullable=False, unique=True),
        sa.Column("original_name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING_REVIEW"),
        sa.ForeignKeyConstraint(["server_id"], ["mcp.servers.id"]),
        sa.UniqueConstraint("server_id", "original_name"),
        schema="mcp",
    )
    op.create_table(
        "tool_versions",
        *_base_columns(),
        sa.Column("tool_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("schema_hash", sa.String(128), nullable=False),
        sa.Column("input_schema", JSONB, nullable=False),
        sa.Column("output_schema", JSONB, nullable=False, server_default="{}"),
        sa.Column("risk_class", sa.String(30), nullable=False, server_default="READ"),
        sa.Column("side_effects", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("idempotent", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("parallel_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("hosted_mcp_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING_REVIEW"),
        sa.ForeignKeyConstraint(["tool_id"], ["mcp.tools.id"]),
        sa.UniqueConstraint("tool_id", "schema_hash"),
        schema="mcp",
    )
    op.create_table(
        "tool_policies",
        *_base_columns(version=True),
        sa.Column("tool_version_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("tenant_id", UUID_TYPE, index=True),
        sa.Column("required_roles", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column(
            "required_purposes", postgresql.ARRAY(sa.String(200)), nullable=False, server_default="{}"
        ),
        sa.Column(
            "required_consents", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"
        ),
        sa.Column(
            "allowed_agents", postgresql.ARRAY(sa.String(150)), nullable=False, server_default="{}"
        ),
        sa.Column("approval_mode", sa.String(30), nullable=False, server_default="POLICY"),
        sa.Column("timeout_seconds", sa.Numeric(8, 3), nullable=False, server_default="30"),
        sa.Column("maximum_result_bytes", sa.Integer(), nullable=False, server_default="262144"),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.ForeignKeyConstraint(["tool_version_id"], ["mcp.tool_versions.id"]),
        schema="mcp",
    )
    op.create_table(
        "agent_tool_grants",
        *_base_columns(version=True),
        sa.Column("agent_version_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("tool_version_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("constraints", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.ForeignKeyConstraint(["tool_version_id"], ["mcp.tool_versions.id"]),
        sa.UniqueConstraint("agent_version_id", "tool_version_id"),
        schema="mcp",
    )
    op.create_table(
        "tool_calls",
        *_base_columns(tenant=True, version=True),
        sa.Column("organization_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("user_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("session_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("run_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("agent_version_id", UUID_TYPE, index=True),
        sa.Column("agent_name", sa.String(150), nullable=False),
        sa.Column("server_id", UUID_TYPE, nullable=False),
        sa.Column("tool_version_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("canonical_name", sa.String(200), nullable=False),
        sa.Column("normalized_arguments", JSONB, nullable=False),
        sa.Column("purpose", sa.String(500), nullable=False),
        sa.Column("resource_refs", postgresql.ARRAY(sa.String(500)), nullable=False, server_default="{}"),
        sa.Column("request_hash", sa.String(128), nullable=False, index=True),
        sa.Column("idempotency_key", sa.String(255), index=True),
        sa.Column("status", sa.String(40), nullable=False, server_default="REQUESTED", index=True),
        sa.Column("guardian_decision_id", UUID_TYPE),
        sa.Column("authorization_id", UUID_TYPE),
        sa.Column("correlation_id", UUID_TYPE, nullable=False, index=True),
        sa.ForeignKeyConstraint(["server_id"], ["mcp.servers.id"]),
        sa.ForeignKeyConstraint(["tool_version_id"], ["mcp.tool_versions.id"]),
        schema="mcp",
    )
    op.create_table(
        "call_attempts",
        *_base_columns(tenant=True),
        sa.Column("call_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("server_version_id", UUID_TYPE),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_class", sa.String(100)),
        sa.Column("error_detail", sa.Text()),
        sa.ForeignKeyConstraint(["call_id"], ["mcp.tool_calls.id"]),
        sa.ForeignKeyConstraint(["server_version_id"], ["mcp.server_versions.id"]),
        sa.UniqueConstraint("tenant_id", "call_id", "attempt_number"),
        schema="mcp",
    )
    op.create_table(
        "tool_results",
        *_base_columns(tenant=True),
        sa.Column("call_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("model_projection", JSONB),
        sa.Column("raw_object_ref", sa.String(1000)),
        sa.Column("raw_hash", sa.String(128)),
        sa.Column("normalized_hash", sa.String(128), nullable=False),
        sa.Column("classification", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.ForeignKeyConstraint(["call_id"], ["mcp.tool_calls.id"]),
        sa.UniqueConstraint("tenant_id", "call_id"),
        schema="mcp",
    )
    op.create_table(
        "health_events",
        *_base_columns(),
        sa.Column("server_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("latency_ms", sa.Integer()),
        sa.Column("error_signal", sa.String(200)),
        sa.Column("circuit_transition", sa.String(50)),
        sa.ForeignKeyConstraint(["server_id"], ["mcp.servers.id"]),
        schema="mcp",
    )

    _enable_rls()
    _repair_runtime_policy_bypass()
    _seed_core_tools()


def _enable_rls() -> None:
    for table in ("tool_calls", "call_attempts", "tool_results"):
        qualified = f'"mcp"."{table}"'
        policy = f"tenant_isolation_mcp_{table}"
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


def _repair_runtime_policy_bypass() -> None:
    scoped = {
        "iam": ["organizations", "users", "memberships", "consents"],
        "conversation": ["sessions", "conversations", "conversation_members", "messages", "provider_state"],
        "agent": ["runs", "run_steps", "run_events"],
        "audit": ["events", "outbox"],
        "ops": ["jobs", "idempotency_keys"],
    }
    for schema, tables in scoped.items():
        for table in tables:
            qualified = f'"{schema}"."{table}"'
            policy = f"tenant_isolation_{schema}_{table}"
            op.execute(sa.text(f"DROP POLICY IF EXISTS {policy} ON {qualified}"))
            op.execute(
                sa.text(
                    f"CREATE POLICY {policy} ON {qualified} USING ("
                    "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
                    "OR current_setting('app.service_role', true) IN ('worker', 'mcp', 'guardian')) "
                    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
                    "OR current_setting('app.service_role', true) IN ('worker', 'mcp', 'guardian'))"
                )
            )


def _schema_hash(input_schema: dict[str, object], output_schema: dict[str, object]) -> str:
    encoded = json.dumps(
        {"input": input_schema, "output": output_schema}, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _seed_core_tools() -> None:
    server_table = sa.table(
        "servers",
        sa.column("id", UUID_TYPE),
        sa.column("tenant_id", UUID_TYPE),
        sa.column("label", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("transport", sa.String()),
        sa.column("endpoint", sa.String()),
        sa.column("auth_type", sa.String()),
        sa.column("trust_tier", sa.String()),
        sa.column("status", sa.String()),
        sa.column("allowed_egress_hosts", postgresql.ARRAY(sa.String())),
        schema="mcp",
    )
    tool_table = sa.table(
        "tools",
        sa.column("id", UUID_TYPE),
        sa.column("server_id", UUID_TYPE),
        sa.column("canonical_name", sa.String()),
        sa.column("original_name", sa.String()),
        sa.column("description", sa.Text()),
        sa.column("status", sa.String()),
        schema="mcp",
    )
    version_table = sa.table(
        "tool_versions",
        sa.column("id", UUID_TYPE),
        sa.column("tool_id", UUID_TYPE),
        sa.column("schema_hash", sa.String()),
        sa.column("input_schema", JSONB),
        sa.column("output_schema", JSONB),
        sa.column("risk_class", sa.String()),
        sa.column("side_effects", sa.Boolean()),
        sa.column("idempotent", sa.Boolean()),
        sa.column("parallel_allowed", sa.Boolean()),
        sa.column("hosted_mcp_allowed", sa.Boolean()),
        sa.column("status", sa.String()),
        schema="mcp",
    )
    policy_table = sa.table(
        "tool_policies",
        sa.column("id", UUID_TYPE),
        sa.column("tool_version_id", UUID_TYPE),
        sa.column("tenant_id", UUID_TYPE),
        sa.column("required_roles", postgresql.ARRAY(sa.String())),
        sa.column("required_purposes", postgresql.ARRAY(sa.String())),
        sa.column("required_consents", postgresql.ARRAY(sa.String())),
        sa.column("allowed_agents", postgresql.ARRAY(sa.String())),
        sa.column("approval_mode", sa.String()),
        sa.column("timeout_seconds", sa.Numeric()),
        sa.column("maximum_result_bytes", sa.Integer()),
        sa.column("status", sa.String()),
        schema="mcp",
    )

    op.bulk_insert(
        server_table,
        [
            {
                "id": CORE_SERVER_ID,
                "tenant_id": None,
                "label": "xyena",
                "description": "Domain-neutral first-party Xyena platform tools.",
                "transport": "IN_PROCESS",
                "endpoint": "http://mcp-server:8081/mcp",
                "auth_type": "SERVICE_TOKEN",
                "trust_tier": "PLATFORM",
                "status": "ACTIVE",
                "allowed_egress_hosts": [],
            }
        ],
    )
    describe_input: dict[str, object] = {"type": "object", "properties": {}, "additionalProperties": False}
    risk_input: dict[str, object] = {
        "type": "object",
        "properties": {
            "risk_class": {"type": "string", "enum": ["READ", "SENSITIVE_READ", "MUTATE", "PRIVILEGED"]}
        },
        "additionalProperties": False,
    }
    output_schema: dict[str, object] = {"type": "object"}
    op.bulk_insert(
        tool_table,
        [
            {
                "id": DESCRIBE_TOOL_ID,
                "server_id": CORE_SERVER_ID,
                "canonical_name": "xyena.platform.describe",
                "original_name": "xyena.platform.describe",
                "description": "Describe Xyena's domain-neutral platform boundary.",
                "status": "ACTIVE",
            },
            {
                "id": RISK_TOOL_ID,
                "server_id": CORE_SERVER_ID,
                "canonical_name": "xyena.tools.explain_risk",
                "original_name": "xyena.tools.explain_risk",
                "description": "Explain Guardian tool risk classes.",
                "status": "ACTIVE",
            },
        ],
    )
    op.bulk_insert(
        version_table,
        [
            {
                "id": DESCRIBE_VERSION_ID,
                "tool_id": DESCRIBE_TOOL_ID,
                "schema_hash": _schema_hash(describe_input, output_schema),
                "input_schema": describe_input,
                "output_schema": output_schema,
                "risk_class": "READ",
                "side_effects": False,
                "idempotent": True,
                "parallel_allowed": True,
                "hosted_mcp_allowed": True,
                "status": "ACTIVE",
            },
            {
                "id": RISK_VERSION_ID,
                "tool_id": RISK_TOOL_ID,
                "schema_hash": _schema_hash(risk_input, output_schema),
                "input_schema": risk_input,
                "output_schema": output_schema,
                "risk_class": "READ",
                "side_effects": False,
                "idempotent": True,
                "parallel_allowed": True,
                "hosted_mcp_allowed": True,
                "status": "ACTIVE",
            },
        ],
    )
    op.bulk_insert(
        policy_table,
        [
            {
                "id": DESCRIBE_POLICY_ID,
                "tool_version_id": DESCRIBE_VERSION_ID,
                "tenant_id": None,
                "required_roles": [],
                "required_purposes": [],
                "required_consents": [],
                "allowed_agents": ["xyena-supervisor"],
                "approval_mode": "NEVER",
                "timeout_seconds": 10,
                "maximum_result_bytes": 32768,
                "status": "ACTIVE",
            },
            {
                "id": RISK_POLICY_ID,
                "tool_version_id": RISK_VERSION_ID,
                "tenant_id": None,
                "required_roles": [],
                "required_purposes": [],
                "required_consents": [],
                "allowed_agents": ["xyena-supervisor"],
                "approval_mode": "NEVER",
                "timeout_seconds": 10,
                "maximum_result_bytes": 32768,
                "status": "ACTIVE",
            },
        ],
    )


def downgrade() -> None:
    op.execute(sa.text('DROP SCHEMA IF EXISTS "mcp" CASCADE'))
