from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB, list[str]: JSONB}


class Item(Base):
    """One learnable thing: a word, phrase or grammar rule."""

    __tablename__ = "items"
    __table_args__ = (UniqueConstraint("lemma", "part_of_speech"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    lemma: Mapped[str] = mapped_column(String(200))
    part_of_speech: Mapped[str] = mapped_column(String(30))
    gender: Mapped[str | None] = mapped_column(String(2))
    forms: Mapped[list[str]]
    forms_display: Mapped[str] = mapped_column(Text)
    meaning_da: Mapped[str] = mapped_column(Text)
    meaning_en: Mapped[str] = mapped_column(Text)
    example: Mapped[str] = mapped_column(Text)
    confusables: Mapped[str | None] = mapped_column(Text)
    explanation_en: Mapped[str | None] = mapped_column(Text)
    uncertain: Mapped[bool] = mapped_column(default=False)
    verified: Mapped[bool] = mapped_column(default=False)
    # set (looked up) -> lærer (learning) -> kan (known), or ignoreret (never quizzed)
    status: Mapped[str] = mapped_column(String(20), default="set")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    lookups: Mapped[list["Lookup"]] = relationship(back_populates="item")


class Lookup(Base):
    """Every lookup, with the exact form sent. A repeat lookup is a sign the word isn't learned."""

    __tablename__ = "lookups"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    query: Mapped[str] = mapped_column(String(300))
    context_sentence: Mapped[str | None] = mapped_column(Text)
    direction: Mapped[str] = mapped_column(String(5))
    used_english: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    item: Mapped[Item] = relationship(back_populates="lookups")


class Document(Base):
    """One upload: a book page, notebook scan, text or question. Filled from M3."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(30))
    file_path: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list[str]] = mapped_column(default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Chunk(Base):
    """A piece of a document's transcribed text. Embeddings are added in M5."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page: Mapped[int | None]
    text: Mapped[str] = mapped_column(Text)


class ItemSource(Base):
    """Where an item came from, so I can go back to the page I first met it on."""

    __tablename__ = "item_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"))
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    chunk_id: Mapped[int | None] = mapped_column(ForeignKey("chunks.id", ondelete="SET NULL"))


def make_sessions(engine: AsyncEngine) -> async_sessionmaker:  # type: ignore[type-arg]
    return async_sessionmaker(engine, expire_on_commit=False)
