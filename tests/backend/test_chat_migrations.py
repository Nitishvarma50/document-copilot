"""Offline DDL and metadata checks, not live PostgreSQL/RLS verification."""

import subprocess
import sys
from pathlib import Path

from app.Database import models
from app.Database.base import Base
from sqlalchemy.orm import configure_mappers

ROOT = Path(__file__).resolve().parents[2]


def test_models_register_chat_tables_and_structured_parts():
    configure_mappers()
    assert {"users", "chat_threads", "chat_messages", "chat_turns"} <= set(
        Base.metadata.tables
    )
    assert not models.ChatMessage.__table__.c.parts.nullable
    active_index = next(
        index
        for index in models.ChatTurn.__table__.indexes
        if index.name == "uq_chat_turns_one_active_thread"
    )
    assert active_index.unique
    assert (
        str(active_index.dialect_options["postgresql"]["where"])
        == "status = 'streaming'"
    )


def test_full_migration_chain_emits_offline_sql():
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"],
        cwd=ROOT / "Backend",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    sql = result.stdout
    assert "CREATE TABLE message_citations" in sql
    assert "CREATE TABLE ix_source_documents_ticker_fiscal_year" not in sql
    assert "CREATE UNIQUE INDEX ix_source_documents_ticker_fiscal_year" in sql
    assert "CREATE TABLE public.chat_turns" in sql
    assert "WHERE status = 'streaming'" in sql
    assert "FOR UPDATE" in sql
    assert "lease_until <= clock_timestamp()" in sql
    assert "SECURITY DEFINER" not in sql
    assert "FROM PUBLIC, anon, authenticated" in sql
    for name in (
        "chat_create_thread",
        "chat_accept_turn",
        "chat_complete_turn",
        "chat_abandon_turn",
    ):
        assert f"CREATE FUNCTION public.{name}" in sql
        assert f"REVOKE ALL ON FUNCTION public.{name}" in sql
        assert f"GRANT EXECUTE ON FUNCTION public.{name}" in sql
    assert "71c9d8a6b402" in sql
