from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for later migrations. Phase 1 has no business tables."""
