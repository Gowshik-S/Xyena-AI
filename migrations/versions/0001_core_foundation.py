"""Core identity, conversation, agent-run, audit, and operations foundation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_core_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())


def _base_columns(*, tenant: bool = True, timestamps: bool = True, version: bool = False) -> list[sa.Column]:
    columns: list[sa.Column] = [sa.Column("id", UUID, primary_key=True)]
    if tenant:
        columns.append(sa.Column("tenant_id", UUID, nullable=False, index=True))
    if version:
        columns.append(sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    if timestamps:
        columns.extend(
            [
                sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            ]
        )
    return columns


def upgrade() -> None:
    for schema in ("iam", "conversation", "agent", "audit", "ops"):
        op.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))

    op.create_table(
        "tenants",
        *_base_columns(tenant=False, version=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.Column("data_region", sa.String(50), nullable=False, server_default="default"),
        sa.Column("policy_bundle_id", sa.String(100), nullable=False, server_default="default"),
        schema="iam",
    )
    op.create_table(
        "organizations",
        *_base_columns(version=True),
        sa.Column("parent_id", UUID, nullable=True),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("organization_type", sa.String(50), nullable=False, server_default="CUSTOMER"),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.ForeignKeyConstraint(["parent_id"], ["iam.organizations.id"]),
        sa.UniqueConstraint("tenant_id", "slug"),
        schema="iam",
    )
    op.create_table(
        "users",
        *_base_columns(version=True),
        sa.Column("idp_subject_hash", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(200)),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.Column("locale", sa.String(20), nullable=False, server_default="en"),
        sa.Column("timezone", sa.String(100), nullable=False, server_default="UTC"),
        sa.UniqueConstraint("tenant_id", "idp_subject_hash"),
        schema="iam",
    )
    op.create_table(
        "memberships",
        *_base_columns(),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("roles", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.ForeignKeyConstraint(["organization_id"], ["iam.organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["iam.users.id"]),
        sa.UniqueConstraint("tenant_id", "organization_id", "user_id"),
        schema="iam",
    )
    op.create_table(
        "consents",
        *_base_columns(version=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("purpose", sa.String(200), nullable=False),
        sa.Column("data_classes", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("proof_ref", sa.Text()),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        schema="iam",
    )
    op.create_table(
        "service_identities",
        *_base_columns(tenant=False, version=True),
        sa.Column("workload_name", sa.String(150), nullable=False, unique=True),
        sa.Column("audience", sa.String(200), nullable=False),
        sa.Column("key_reference", sa.String(500), nullable=False),
        sa.Column("scopes", postgresql.ARRAY(sa.String(150)), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        schema="iam",
    )

    op.create_table(
        "sessions",
        *_base_columns(version=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        schema="conversation",
    )
    op.create_table(
        "conversations",
        *_base_columns(version=True),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE"),
        sa.Column("model_policy_id", sa.String(100), nullable=False, server_default="default"),
        sa.ForeignKeyConstraint(["session_id"], ["conversation.sessions.id"]),
        schema="conversation",
    )
    op.create_table(
        "conversation_members",
        *_base_columns(),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("member_role", sa.String(50), nullable=False, server_default="OWNER"),
        sa.Column("left_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.conversations.id"]),
        sa.UniqueConstraint("tenant_id", "conversation_id", "user_id"),
        schema="conversation",
    )
    op.create_table(
        "messages",
        *_base_columns(version=False),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("text_content", sa.Text()),
        sa.Column("structured_content", JSONB),
        sa.Column("sensitivity", sa.String(30), nullable=False, server_default="INTERNAL"),
        sa.Column("supersedes_id", UUID),
        sa.Column("metadata", JSONB, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversation.conversations.id"]),
        sa.UniqueConstraint("tenant_id", "conversation_id", "sequence"),
        schema="conversation",
    )
    op.create_table(
        "provider_state",
        *_base_columns(version=True),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("provider_conversation_id", sa.String(255)),
        sa.Column("previous_response_id", sa.String(255)),
        sa.Column("encrypted_state", sa.Text()),
        sa.UniqueConstraint("tenant_id", "conversation_id", "provider"),
        schema="conversation",
    )

    op.create_table(
        "definitions",
        *_base_columns(tenant=False, version=True),
        sa.Column("stable_name", sa.String(100), nullable=False, unique=True),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("owner", sa.String(200), nullable=False, server_default="platform"),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        schema="agent",
    )
    op.create_table(
        "versions",
        *_base_columns(tenant=False),
        sa.Column("definition_id", UUID, nullable=False),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("instructions_ref", sa.String(500), nullable=False),
        sa.Column("instructions_hash", sa.String(128), nullable=False),
        sa.Column("model_policy", JSONB, nullable=False, server_default="{}"),
        sa.Column("output_schema", JSONB, nullable=False, server_default="{}"),
        sa.Column("context_profile", JSONB, nullable=False, server_default="{}"),
        sa.Column("budgets", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.ForeignKeyConstraint(["definition_id"], ["agent.definitions.id"]),
        sa.UniqueConstraint("definition_id", "version"),
        schema="agent",
    )
    op.create_table(
        "runs",
        *_base_columns(version=True),
        sa.Column("organization_id", UUID, nullable=False),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("session_id", UUID, nullable=False),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("case_id", UUID),
        sa.Column("correlation_id", UUID, nullable=False),
        sa.Column("start_agent", sa.String(100), nullable=False, server_default="xyena-supervisor"),
        sa.Column("status", sa.String(40), nullable=False, server_default="QUEUED"),
        sa.Column("input_message_id", UUID),
        sa.Column("result_message_id", UUID),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_detail", sa.Text()),
        sa.Column("usage", JSONB, nullable=False, server_default="{}"),
        sa.Column("lease_owner", sa.String(200)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        schema="agent",
    )
    op.create_table(
        "run_steps",
        *_base_columns(),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("step_type", sa.String(50), nullable=False),
        sa.Column("agent_version_id", UUID),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("input_ref", sa.String(500)),
        sa.Column("output_ref", sa.String(500)),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["run_id"], ["agent.runs.id"]),
        sa.UniqueConstraint("tenant_id", "run_id", "sequence"),
        schema="agent",
    )
    op.create_table(
        "run_events",
        *_base_columns(timestamps=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(40), nullable=False),
        sa.Column("data", JSONB, nullable=False, server_default="{}"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent.runs.id"]),
        sa.UniqueConstraint("tenant_id", "run_id", "sequence"),
        schema="agent",
    )

    op.create_table(
        "events",
        *_base_columns(timestamps=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("actor_type", sa.String(30), nullable=False),
        sa.Column("actor_id", sa.String(200), nullable=False),
        sa.Column("event_type", sa.String(150), nullable=False),
        sa.Column("subject_type", sa.String(100), nullable=False),
        sa.Column("subject_id", UUID, nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("correlation_id", UUID, nullable=False),
        sa.Column("previous_hash", sa.String(128)),
        sa.Column("event_hash", sa.String(128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "sequence"),
        schema="audit",
    )
    op.create_table(
        "outbox",
        *_base_columns(timestamps=False),
        sa.Column("aggregate_type", sa.String(100), nullable=False),
        sa.Column("aggregate_id", UUID, nullable=False),
        sa.Column("aggregate_version", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("event_type", sa.String(150), nullable=False),
        sa.Column("schema_version", sa.String(30), nullable=False, server_default="1.0"),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("correlation_id", UUID, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text()),
        schema="audit",
    )
    op.create_table(
        "jobs",
        *_base_columns(version=True),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("state", sa.String(30), nullable=False, server_default="AVAILABLE"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("lease_owner", sa.String(200)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        schema="ops",
    )
    op.create_table(
        "idempotency_keys",
        *_base_columns(),
        sa.Column("operation", sa.String(150), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(128), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="IN_PROGRESS"),
        sa.Column("result_ref", UUID),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "operation", "key"),
        schema="ops",
    )

    _enable_tenant_rls()
    _create_runtime_roles()


def _enable_tenant_rls() -> None:
    scoped_tables = {
        "iam": ["organizations", "users", "memberships", "consents"],
        "conversation": ["sessions", "conversations", "conversation_members", "messages", "provider_state"],
        "agent": ["runs", "run_steps", "run_events"],
        "audit": ["events", "outbox"],
        "ops": ["jobs", "idempotency_keys"],
    }
    for schema, tables in scoped_tables.items():
        for table in tables:
            qualified = f'"{schema}"."{table}"'
            policy = f"tenant_isolation_{schema}_{table}"
            op.execute(sa.text(f"ALTER TABLE {qualified} ENABLE ROW LEVEL SECURITY"))
            op.execute(sa.text(f"ALTER TABLE {qualified} FORCE ROW LEVEL SECURITY"))
            op.execute(
                sa.text(
                    f"CREATE POLICY {policy} ON {qualified} USING ("
                    "tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
                    "OR current_user IN ('xyena_worker', 'xyena_mcp', 'xyena_guardian')) "
                    "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid "
                    "OR current_user IN ('xyena_worker', 'xyena_mcp', 'xyena_guardian'))"
                )
            )


def _create_runtime_roles() -> None:
    op.execute(
        sa.text(
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'xyena_api') THEN CREATE ROLE xyena_api NOLOGIN; END IF; "
            "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'xyena_worker') THEN CREATE ROLE xyena_worker NOLOGIN; END IF; "
            "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'xyena_mcp') THEN CREATE ROLE xyena_mcp NOLOGIN; END IF; "
            "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'xyena_guardian') THEN CREATE ROLE xyena_guardian NOLOGIN; END IF; "
            "END $$"
        )
    )


def downgrade() -> None:
    for schema in ("ops", "audit", "agent", "conversation", "iam"):
        op.execute(sa.text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
