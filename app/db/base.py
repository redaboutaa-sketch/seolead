"""Declarative base and portable column types.

The types are declared as generic SQLAlchemy types with a PostgreSQL variant.
Production is PostgreSQL; the test suite runs the same models on SQLite so the
persistence layer can be tested without a database container. Anything that only
works on one of the two would defeat that, so JSONB and native UUID are expressed
as variants rather than hard dependencies.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, mapped_column

JSONType = JSON().with_variant(JSONB, "postgresql")
UUIDType = Uuid(as_uuid=True)
TZDateTime = DateTime(timezone=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


def pk_column():
    return mapped_column(UUIDType, primary_key=True, default=uuid.uuid4)


def created_column():
    return mapped_column(TZDateTime, nullable=False, server_default=func.now(),
                         default=utcnow)


def updated_column():
    return mapped_column(TZDateTime, nullable=False, server_default=func.now(),
                         default=utcnow, onupdate=utcnow)
