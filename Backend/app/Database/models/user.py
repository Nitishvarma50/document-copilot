from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from app.Database.base import Base, TimestampMixin
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.Database.models.chat_thread import ChatThread


class User(Base, TimestampMixin):
    """One row per user for management and authentication."""

    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(225), nullable=True)

    chat_threads: Mapped[list[ChatThread]] = relationship(back_populates="owner")
