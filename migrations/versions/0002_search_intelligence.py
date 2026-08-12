"""Phase 3 — search intelligence, relevance gate, claim risk.

Additive throughout. Every new column on an existing table is nullable or carries
a server default, so Phase 2 rows remain valid and readable: a V1 package is still
a V1 package, and `package_version` says so rather than leaving the reader to
guess from which columns happen to be populated.

Revision ID: 0002_search
Revises: 0001_initial
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_search"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    # ── SERP intelligence ────────────────────────────────────────────────────
    op.create_table(
        "serp_snapshot",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("keyword_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("seed_keyword.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("cache_key", sa.String(128), nullable=False),
        sa.Column("location_code", sa.Integer(), nullable=False),
        sa.Column("location_name", sa.String(128), nullable=False),
        sa.Column("language_code", sa.String(8), nullable=False),
        sa.Column("device", sa.String(16), nullable=False),
        sa.Column("se_domain", sa.String(64), nullable=True),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("total_items", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("organic_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provider_cost_usd", sa.Float(), nullable=True),
        sa.Column("analysis", JSONB, nullable=False, server_default="{}"),
        sa.Column("provider_metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_serp_snapshot_keyword", "serp_snapshot", ["keyword_id"])
    op.create_index("ix_serp_snapshot_lookup", "serp_snapshot",
                    ["cache_key", "retrieved_at"])

    op.create_table(
        "serp_result",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("serp_snapshot_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("serp_snapshot.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("rank_group", sa.Integer(), nullable=True),
        sa.Column("rank_absolute", sa.Integer(), nullable=True),
        sa.Column("result_type", sa.String(64), nullable=False),
        sa.Column("is_organic", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("domain", sa.String(255), nullable=True),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("breadcrumb", sa.Text(), nullable=True),
        sa.Column("shape", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_serp_result_snapshot", "serp_result", ["serp_snapshot_id"])

    op.create_table(
        "serp_question",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("serp_snapshot_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("serp_snapshot.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("rank_absolute", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('PAA', 'RELATED')", name="ck_serp_question_kind"),
    )
    op.create_index("ix_serp_question_snapshot", "serp_question",
                    ["serp_snapshot_id"])

    # ── Keyword metrics ──────────────────────────────────────────────────────
    # `observability` is CHECK-constrained for the same reason it is on evidence:
    # a volume figure with no stated source is indistinguishable from an invented
    # one, and the mission forbids inventing them.
    op.create_table(
        "keyword_metric",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("keyword_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("seed_keyword.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("metric_type", sa.String(64), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("value_text", sa.String(64), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("observability", sa.String(16), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric_metadata", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("observability IN ('OBSERVED', 'ESTIMATED', 'UNKNOWN')",
                           name="ck_keyword_metric_observability"),
    )
    op.create_index("ix_keyword_metric_keyword", "keyword_metric", ["keyword_id"])

    # ── Opportunity score ────────────────────────────────────────────────────
    op.create_table(
        "seo_opportunity",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("keyword_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("seed_keyword.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("score_version", sa.String(16), nullable=False),
        sa.Column("components", JSONB, nullable=False, server_default="[]"),
        sa.Column("missing_inputs", JSONB, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint(
            "overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 100)",
            name="ck_opportunity_score_range"),
    )
    op.create_index("ix_seo_opportunity_keyword", "seo_opportunity", ["keyword_id"])

    # ── Provider usage ───────────────────────────────────────────────────────
    op.create_table(
        "provider_usage",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("requests", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("units", sa.Integer(), nullable=True),
        # Nullable, not zero: Tavily and OpenAI return no monetary cost, and
        # recording 0.0 would claim a job was free when its cost is unknown.
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("cost_is_actual", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_provider_usage_correlation", "provider_usage",
                    ["correlation_id"])

    # ── research_source: relevance gate ──────────────────────────────────────
    for column in (
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("relevance_status", sa.String(16), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=True),
        sa.Column("relevance_reason", sa.Text(), nullable=True),
        sa.Column("source_quality", sa.String(16), nullable=True),
    ):
        op.add_column("research_source", column)

    op.create_check_constraint(
        "ck_research_source_relevance",
        "research_source",
        "relevance_status IS NULL OR relevance_status IN "
        "('RELEVANT', 'LOW_RELEVANCE', 'IRRELEVANT', 'UNKNOWN')",
    )
    op.create_check_constraint(
        "ck_research_source_quality",
        "research_source",
        "source_quality IS NULL OR source_quality IN "
        "('OFFICIAL', 'INSTITUTIONAL', 'SPECIALIST', 'COMMERCIAL', 'COMMUNITY', "
        "'UNKNOWN')",
    )

    # ── research_evidence: claim risk ────────────────────────────────────────
    for column in (
        sa.Column("claim_risk", sa.String(16), nullable=True),
        sa.Column("support_status", sa.String(24), nullable=True),
        sa.Column("evidence_sufficient", sa.Boolean(), nullable=True),
    ):
        op.add_column("research_evidence", column)

    op.create_check_constraint(
        "ck_research_evidence_claim_risk", "research_evidence",
        "claim_risk IS NULL OR claim_risk IN ('LOW', 'MEDIUM', 'HIGH')",
    )
    op.create_check_constraint(
        "ck_research_evidence_support", "research_evidence",
        "support_status IS NULL OR support_status IN "
        "('SUPPORTED', 'PARTIALLY_SUPPORTED', 'UNSUPPORTED', 'CONFLICTING')",
    )

    # ── research_package: V2 fields ──────────────────────────────────────────
    op.add_column("research_package",
                  sa.Column("package_version", sa.Integer(), nullable=False,
                            server_default="1"))
    op.add_column("research_package",
                  sa.Column("serp_snapshot_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("research_package",
                  sa.Column("seo_opportunity_id", sa.Uuid(as_uuid=True),
                            nullable=True))
    op.create_foreign_key("fk_package_serp_snapshot", "research_package",
                          "serp_snapshot", ["serp_snapshot_id"], ["id"],
                          ondelete="SET NULL")
    op.create_foreign_key("fk_package_opportunity", "research_package",
                          "seo_opportunity", ["seo_opportunity_id"], ["id"],
                          ondelete="SET NULL")

    for name, default in (
        ("eligible_evidence", "[]"), ("rejected_evidence", "[]"),
        ("competitor_pages", "[]"), ("serp_observations", "[]"),
        ("serp_features", "[]"), ("content_gap", "[]"),
        ("related_searches", "[]"), ("keyword_metrics", "[]"),
    ):
        op.add_column("research_package",
                      sa.Column(name, JSONB, nullable=False, server_default=default))
    for name in ("source_quality_summary", "claim_risk_summary"):
        op.add_column("research_package",
                      sa.Column(name, JSONB, nullable=False, server_default="{}"))


def downgrade() -> None:
    for name in ("source_quality_summary", "claim_risk_summary",
                 "eligible_evidence", "rejected_evidence", "competitor_pages",
                 "serp_observations", "serp_features", "content_gap",
                 "related_searches", "keyword_metrics"):
        op.drop_column("research_package", name)
    op.drop_constraint("fk_package_opportunity", "research_package",
                       type_="foreignkey")
    op.drop_constraint("fk_package_serp_snapshot", "research_package",
                       type_="foreignkey")
    op.drop_column("research_package", "seo_opportunity_id")
    op.drop_column("research_package", "serp_snapshot_id")
    op.drop_column("research_package", "package_version")

    op.drop_constraint("ck_research_evidence_support", "research_evidence",
                       type_="check")
    op.drop_constraint("ck_research_evidence_claim_risk", "research_evidence",
                       type_="check")
    for name in ("evidence_sufficient", "support_status", "claim_risk"):
        op.drop_column("research_evidence", name)

    op.drop_constraint("ck_research_source_quality", "research_source", type_="check")
    op.drop_constraint("ck_research_source_relevance", "research_source",
                       type_="check")
    for name in ("source_quality", "relevance_reason", "relevance_score",
                 "relevance_status", "provider"):
        op.drop_column("research_source", name)

    for table in ("provider_usage", "seo_opportunity", "keyword_metric",
                  "serp_question", "serp_result", "serp_snapshot"):
        op.drop_table(table)
