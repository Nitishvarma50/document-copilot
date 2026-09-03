"""Shared SQLAlchemy base classes used by the application's database models."""

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Parent class for every SQLAlchemy model in the application.

    Models that inherit from this class are registered in ``Base.metadata``.
    Alembic uses that metadata to discover tables and generate migrations.
    """

    pass


class TimestampMixin:
    """Provide reusable creation and modification timestamp columns.

    Add this mixin to models that need ``created_at`` and ``updated_at``:

        class ChatThread(TimestampMixin, Base):
            __tablename__ = "chat_threads"
    """

    # ``Mapped[datetime]`` describes the Python type exposed on model objects.
    # ``timezone=True`` creates a timezone-aware database timestamp.
    # ``server_default=func.now()`` asks PostgreSQL—not Python—to set the
    # insertion time when the application does not provide a value.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # This default initializes updated_at when the row is first inserted.
    # It does not automatically change on later updates. Add
    # ``onupdate=func.now()`` for SQLAlchemy-managed updates, or use a database
    # trigger if every update must refresh the timestamp regardless of source.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        onupdate=func.now(),
    )
