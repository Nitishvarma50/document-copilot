"""Register every application table in the metadata consumed by Alembic."""

from app.Database.models.chat_messages import ChatMessage
from app.Database.models.chat_thread import ChatThread
from app.Database.models.chat_turn import ChatTurn
from app.Database.models.document_chunk import DocumentChunk
from app.Database.models.document_table import DocumentTable
from app.Database.models.message_citation import MessageCitation
from app.Database.models.source_document import SourceDocument
from app.Database.models.user import User

__all__ = [
    "ChatMessage",
    "ChatThread",
    "ChatTurn",
    "DocumentChunk",
    "DocumentTable",
    "MessageCitation",
    "SourceDocument",
    "User",
]
