"""Database-backed turn reservations; accessible only to the backend writer."""

import uuid
from datetime import datetime

from app.Database.base import Base
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class ChatTurn(Base):
    __tablename__ = "chat_turns"
    __table_args__ = (
        UniqueConstraint("thread_id", "assistant_sequence"),
        CheckConstraint("assistant_sequence > 0"),
        CheckConstraint("status IN ('streaming', 'completed', 'interrupted')"),
        Index(
            "uq_chat_turns_one_active_thread",
            "thread_id",
            unique=True,
            postgresql_where=text("status = 'streaming'"),
        ),
    )

    message_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_messages.id", ondelete="CASCADE"),
        primary_key=True,
    )
    thread_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    assistant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
    )
    assistant_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    lease_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
