"""Shared declarative base for PostgreSQL mappings."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
