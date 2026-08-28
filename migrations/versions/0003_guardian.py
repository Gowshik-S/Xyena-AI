"""Independent Guardian policy, decisions, approvals, and authorizations."""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_guardian"
down_revision: str | None = "0002_mcp_gateway"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID_TYPE = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())
POLICY_BUNDLE_ID = UUID("20000000-0000-4000-8000-000000000001")


def _base_columns(*, tenant: bool = False, version: bool = False) -> list[sa.Column]:
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
    op.execute(sa.text('CREATE SCHEMA IF NOT EXISTS "guardian"'))
    op.create_table(
        "policy_bundles",
        *_base_columns(version=True),
        sa.Column("stable_name", sa.String(100), nullable=False),
        sa.Column("bundle_version", sa.String(100), nullable=False),
        sa.Column("document", JSONB, nullable=False),
        sa.Column("document_hash", sa.String(128), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("stable_name", "bundle_version"),
        schema="guardian",
    )
    op.create_table(
        "decisions",
        *_base_columns(tenant=True),
        sa.Column("organization_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("user_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("run_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("tool_call_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("request_hash", sa.String(128), nullable=False, index=True),
        sa.Column("evaluation_hash", sa.String(128), nullable=False),
        sa.Column("policy_bundle_version", sa.String(100), nullable=False),
        sa.Column("risk_class", sa.String(30), nullable=False),
        sa.Column("outcome", sa.String(30), nullable=False, index=True),
        sa.Column("reason_codes", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("constraints", JSONB, nullable=False, server_default="{}"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        schema="guardian",
    )
    op.create_table(
        "approval_requests",
        *_base_columns(tenant=True, version=True),
        sa.Column("decision_id", UUID_TYPE, nullable=False, unique=True, index=True),
        sa.Column("tool_call_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("requested_for_user_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("risk_class", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING", index=True),
        sa.Column(
            "required_approver_roles", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["decision_id"], ["guardian.decisions.id"]),
        schema="guardian",
    )
    op.create_table(
        "approval_actions",
        *_base_columns(tenant=True),
        sa.Column("approval_request_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("actor_user_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("actor_roles", postgresql.ARRAY(sa.String(100)), nullable=False, server_default="{}"),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("correlation_id", UUID_TYPE, nullable=False, index=True),
        sa.ForeignKeyConstraint(["approval_request_id"], ["guardian.approval_requests.id"]),
        schema="guardian",
    )
    op.create_table(
        "authorizations",
        *_base_columns(tenant=True),
        sa.Column("decision_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("tool_call_id", UUID_TYPE, nullable=False, index=True),
        sa.Column("request_hash", sa.String(128), nullable=False, index=True),
        sa.Column("token_id", UUID_TYPE, nullable=False, unique=True),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("constraints", JSONB, nullable=False, server_default="{}"),
        sa.Column("status", sa.String(30), nullable=False, server_default="ACTIVE", index=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("consumed_correlation_id", UUID_TYPE),
        sa.ForeignKeyConstraint(["decision_id"], ["guardian.decisions.id"]),
        schema="guardian",
    )
    _enable_rls()
    _seed_policy_bundle()


def _enable_rls() -> None:
    for table in ("decisions", "approval_requests", "approval_actions", "authorizations"):
        qualified = f'"guardian"."{table}"'
        policy = f"tenant_isolation_guardian_{table}"
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


def _seed_policy_bundle() -> None:
    document = {
        "version": "platform-default-v1",
        "default": "BLOCK",
        "rules": {
            "READ": "ALLOW only for active policy with approval NEVER",
            "SENSITIVE_READ": "ALLOW only with role, purpose, consent and exact authorization",
            "MUTATE": "ALLOW only with idempotency and exact authorization",
            "PRIVILEGED": "Always require human approval and exact authorization",
        },
    }
    document_hash = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    table = sa.table(
        "policy_bundles",
        sa.column("id", UUID_TYPE),
        sa.column("stable_name", sa.String()),
        sa.column("bundle_version", sa.String()),
        sa.column("document", JSONB),
        sa.column("document_hash", sa.String()),
        sa.column("status", sa.String()),
        sa.column("activated_at", sa.DateTime(timezone=True)),
        schema="guardian",
    )
    op.bulk_insert(
        table,
        [
            {
                "id": POLICY_BUNDLE_ID,
                "stable_name": "platform-default",
                "bundle_version": "platform-default-v1",
                "document": document,
                "document_hash": document_hash,
                "status": "ACTIVE",
                "activated_at": datetime.now(UTC),
            }
        ],
    )


def downgrade() -> None:
    op.execute(sa.text('DROP SCHEMA IF EXISTS "guardian" CASCADE'))
