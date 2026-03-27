"""Add scheduled jobs and execution trigger source.

Revision ID: 20260327_000007
Revises: 20260326_000006
Create Date: 2026-03-27 10:30:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260327_000007"
down_revision = "20260326_000006"
branch_labels = None
depends_on = None


execution_trigger_source_enum = sa.Enum("manual", "schedule", name="executiontriggersource")
scheduled_job_concurrency_policy_enum = sa.Enum("forbid", "allow", "replace", name="scheduledjobconcurrencypolicy")
scheduled_job_misfire_policy_enum = sa.Enum("skip", "fire_once", name="scheduledjobmisfirepolicy")
scheduled_job_run_status_enum = sa.Enum("triggered", "skipped", "failed", name="scheduledjobrunstatus")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if bind.dialect.name != "sqlite":
        execution_trigger_source_enum.create(bind, checkfirst=True)

    if not inspector.has_table("scheduled_jobs"):
        op.create_table(
            "scheduled_jobs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("suite_id", sa.Integer(), nullable=False),
            sa.Column("environment_id", sa.Integer(), nullable=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("cron_expr", sa.String(length=128), nullable=False),
            sa.Column("timezone", sa.String(length=64), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_triggered_execution_id", sa.Integer(), nullable=True),
            sa.Column(
                "concurrency_policy",
                scheduled_job_concurrency_policy_enum,
                nullable=False,
                server_default="forbid",
            ),
            sa.Column(
                "misfire_policy",
                scheduled_job_misfire_policy_enum,
                nullable=False,
                server_default="skip",
            ),
            sa.Column("created_by_user_id", sa.Integer(), nullable=True),
            sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["suite_id"], ["suites.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["last_triggered_execution_id"], ["executions.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_scheduled_jobs_project_id", "scheduled_jobs", ["project_id"], unique=False)
        op.create_index("ix_scheduled_jobs_suite_id", "scheduled_jobs", ["suite_id"], unique=False)
        op.create_index("ix_scheduled_jobs_environment_id", "scheduled_jobs", ["environment_id"], unique=False)

    if not inspector.has_table("scheduled_job_runs"):
        op.create_table(
            "scheduled_job_runs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("scheduled_job_id", sa.Integer(), nullable=False),
            sa.Column("planned_run_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("execution_id", sa.Integer(), nullable=True),
            sa.Column("status", scheduled_job_run_status_enum, nullable=False, server_default="triggered"),
            sa.Column("message", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["scheduled_job_id"], ["scheduled_jobs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["execution_id"], ["executions.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("scheduled_job_id", "planned_run_at", name="uq_scheduled_job_runs_job_planned_run_at"),
        )
        op.create_index("ix_scheduled_job_runs_scheduled_job_id", "scheduled_job_runs", ["scheduled_job_id"], unique=False)

    execution_columns = {column["name"] for column in inspector.get_columns("executions")}
    with op.batch_alter_table("executions") as batch_op:
        if "trigger_source" not in execution_columns:
            batch_op.add_column(
                sa.Column(
                    "trigger_source",
                    execution_trigger_source_enum,
                    nullable=False,
                    server_default="manual",
                )
            )
        if "scheduled_job_id" not in execution_columns:
            batch_op.add_column(sa.Column("scheduled_job_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_executions_scheduled_job_id",
                "scheduled_jobs",
                ["scheduled_job_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if "scheduled_run_id" not in execution_columns:
            batch_op.add_column(sa.Column("scheduled_run_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_executions_scheduled_run_id",
                "scheduled_job_runs",
                ["scheduled_run_id"],
                ["id"],
                ondelete="SET NULL",
            )

    current_indexes = {item["name"] for item in inspector.get_indexes("executions")}
    if "ix_executions_scheduled_job_id" not in current_indexes:
        op.create_index("ix_executions_scheduled_job_id", "executions", ["scheduled_job_id"], unique=False)
    if "ix_executions_scheduled_run_id" not in current_indexes:
        op.create_index("ix_executions_scheduled_run_id", "executions", ["scheduled_run_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    execution_columns = {column["name"] for column in inspector.get_columns("executions")}
    execution_indexes = {item["name"] for item in inspector.get_indexes("executions")}
    with op.batch_alter_table("executions") as batch_op:
        if "ix_executions_scheduled_run_id" in execution_indexes:
            batch_op.drop_index("ix_executions_scheduled_run_id")
        if "ix_executions_scheduled_job_id" in execution_indexes:
            batch_op.drop_index("ix_executions_scheduled_job_id")
        if "scheduled_run_id" in execution_columns:
            batch_op.drop_constraint("fk_executions_scheduled_run_id", type_="foreignkey")
            batch_op.drop_column("scheduled_run_id")
        if "scheduled_job_id" in execution_columns:
            batch_op.drop_constraint("fk_executions_scheduled_job_id", type_="foreignkey")
            batch_op.drop_column("scheduled_job_id")
        if "trigger_source" in execution_columns:
            batch_op.drop_column("trigger_source")

    if inspector.has_table("scheduled_job_runs"):
        run_indexes = {item["name"] for item in inspector.get_indexes("scheduled_job_runs")}
        if "ix_scheduled_job_runs_scheduled_job_id" in run_indexes:
            op.drop_index("ix_scheduled_job_runs_scheduled_job_id", table_name="scheduled_job_runs")
        op.drop_table("scheduled_job_runs")

    if inspector.has_table("scheduled_jobs"):
        job_indexes = {item["name"] for item in inspector.get_indexes("scheduled_jobs")}
        for index_name in [
            "ix_scheduled_jobs_environment_id",
            "ix_scheduled_jobs_suite_id",
            "ix_scheduled_jobs_project_id",
        ]:
            if index_name in job_indexes:
                op.drop_index(index_name, table_name="scheduled_jobs")
        op.drop_table("scheduled_jobs")

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        scheduled_job_run_status_enum.drop(bind, checkfirst=True)
        scheduled_job_misfire_policy_enum.drop(bind, checkfirst=True)
        scheduled_job_concurrency_policy_enum.drop(bind, checkfirst=True)
        execution_trigger_source_enum.drop(bind, checkfirst=True)
