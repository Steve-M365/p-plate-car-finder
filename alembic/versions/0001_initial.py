"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cars",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("make", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("variant", sa.String(length=120), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("engine_size_cc", sa.Integer(), nullable=True),
        sa.Column("power_kw", sa.Float(), nullable=True),
        sa.Column("weight_kg", sa.Integer(), nullable=True),
        sa.Column("power_to_weight", sa.Float(), nullable=True),
        sa.Column("body_type", sa.String(length=40), nullable=True),
        sa.Column("fuel_type", sa.String(length=40), nullable=True),
        sa.Column("transmission", sa.String(length=40), nullable=True),
        sa.Column("cylinders", sa.Integer(), nullable=True),
        sa.Column("price_aud", sa.Integer(), nullable=True),
        sa.Column("odometer_km", sa.Integer(), nullable=True),
        sa.Column("location", sa.String(length=120), nullable=True),
        sa.Column("safety_rating_stars", sa.Float(), nullable=True),
        sa.Column("safety_rating_year", sa.Integer(), nullable=True),
        sa.Column("listing_url", sa.String(length=500), nullable=True),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("p_plate_compliant", sa.String(length=24), nullable=False),
        sa.Column("p_plate_reason", sa.Text(), nullable=True),
        sa.Column("listed_high_performance", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("modified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("modification_notes", sa.Text(), nullable=True),
        sa.Column("recommended", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_cars_make", "cars", ["make"])
    op.create_index("ix_cars_model", "cars", ["model"])
    op.create_index("ix_cars_year", "cars", ["year"])
    op.create_index("ix_cars_body_type", "cars", ["body_type"])
    op.create_index("ix_cars_fuel_type", "cars", ["fuel_type"])
    op.create_index("ix_cars_price_aud", "cars", ["price_aud"])
    op.create_index("ix_cars_p_plate_compliant", "cars", ["p_plate_compliant"])
    op.create_index("ix_cars_recommended", "cars", ["recommended"])
    op.create_index("ix_cars_external_id", "cars", ["external_id"])

    op.create_table(
        "recommendation_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("url", sa.String(length=500), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=40), nullable=True),
        sa.Column("query", sa.String(length=300), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_recommendation_sources_category", "recommendation_sources", ["category"])

    op.create_table(
        "search_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("query", sa.String(length=400), nullable=False),
        sa.Column("provider", sa.String(length=60), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_search_runs_run_at", "search_runs", ["run_at"])

    op.create_table(
        "fetch_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("query", sa.String(length=400), nullable=True),
        sa.Column("fetched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="ok"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fetch_runs_run_at", "fetch_runs", ["run_at"])

    op.create_table(
        "external_request_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("method", sa.String(length=10), nullable=False),
        sa.Column("url", sa.String(length=800), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("cached", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allowed_by_robots", sa.Boolean(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("external_request_log")
    op.drop_index("ix_fetch_runs_run_at", table_name="fetch_runs")
    op.drop_table("fetch_runs")
    op.drop_index("ix_search_runs_run_at", table_name="search_runs")
    op.drop_table("search_runs")
    op.drop_index("ix_recommendation_sources_category", table_name="recommendation_sources")
    op.drop_table("recommendation_sources")
    for idx in (
        "ix_cars_external_id",
        "ix_cars_recommended",
        "ix_cars_p_plate_compliant",
        "ix_cars_price_aud",
        "ix_cars_fuel_type",
        "ix_cars_body_type",
        "ix_cars_year",
        "ix_cars_model",
        "ix_cars_make",
    ):
        op.drop_index(idx, table_name="cars")
    op.drop_table("cars")
