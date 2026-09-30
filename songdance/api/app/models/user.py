from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(254))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AuthIdentity(TimestampMixin, Base):
    __tablename__ = "auth_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_auth_issuer_subject"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    issuer: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(36), nullable=False)
