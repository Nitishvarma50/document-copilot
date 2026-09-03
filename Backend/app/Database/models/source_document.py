from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from app.Database.base import Base, TimestampMixin
from sqlalchemy import (
    Date,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.Database.models.document_chunk import DocumentChunk
    from app.Database.models.document_table import DocumentTable


class SourceDocument(Base, TimestampMixin):
    """Normalized filing stored for chunking , retrieval and citation."""

    __tablename__ = "source_documents"
    __table_args__ = (
        UniqueConstraint(
            "accession_number", name="uq_source_documents_accession_number_version"
        ),
        Index("ix_source_documents_accession_number", "accession_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=True, index=True)
    cik: Mapped[str] = mapped_column(String(10), nullable=True, index=True)
    company_name: Mapped[str] = mapped_column(String(256), nullable=True)
    form: Mapped[str] = mapped_column(String(16), nullable=True, index=True)
    filing_date: Mapped[date] = mapped_column(Date, nullable=True, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=True, index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=True, index=True)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=True, index=True)
    primary_document: Mapped[str] = mapped_column(String(256), nullable=True)
    source_url: Mapped[str] = mapped_column(String(512), nullable=True)
    markdown_content: Mapped[str] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )

    tables: Mapped[list[DocumentTable]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
