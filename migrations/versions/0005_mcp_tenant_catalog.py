"""Allow tenant-local MCP catalogs to reuse canonical tool names safely."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0005_mcp_tenant_catalog"
down_revision: str | None = "0004_context_memory_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_tools_canonical_name", "tools", schema="mcp", type_="unique")
    op.create_unique_constraint(
        "uq_mcp_tools_server_canonical_name",
        "tools",
        ["server_id", "canonical_name"],
        schema="mcp",
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_mcp_tools_server_canonical_name", "tools", schema="mcp", type_="unique"
    )
    op.create_unique_constraint(
        "uq_tools_canonical_name", "tools", ["canonical_name"], schema="mcp"
    )
