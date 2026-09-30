from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID, uuid4

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import AuthIdentity, User
from app.settings import Settings


def auth_error(status: int = 401, code: str = "AUTH_INVALID") -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "message": "Authentication unavailable or invalid"},
    )


@dataclass(frozen=True)
class VerifiedIdentity:
    issuer: str
    subject: str
    email: str | None


class SupabaseVerifier:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.issuer = settings.supabase_url.rstrip("/") + "/auth/v1"
        self.jwks = jwt.PyJWKClient(
            self.issuer + "/.well-known/jwks.json",
            lifespan=300,
            timeout=5,
        )
        dsn = settings.auth_session_database_url.get_secret_value().replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
        self.engine = create_engine(dsn, pool_pre_ping=True, connect_args={"connect_timeout": 5})

    def verify(self, token: str) -> VerifiedIdentity:
        try:
            key = self.jwks.get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["ES256", "RS256"],
                issuer=self.issuer,
                audience="authenticated",
                options={"require": ["exp", "iss", "aud", "sub", "session_id"]},
            )
            if not isinstance(claims["sub"], str) or not isinstance(claims["session_id"], str):
                raise ValueError("identity claims must be strings")
            subject = str(UUID(claims["sub"]))
            session_id = str(UUID(claims["session_id"]))
            if claims.get("role") != "authenticated":
                raise ValueError("role")
        except jwt.PyJWKClientConnectionError:
            raise auth_error(503, "AUTH_UNAVAILABLE") from None
        except (jwt.PyJWTError, ValueError, TypeError, KeyError):
            raise auth_error() from None
        if not self.session_active(subject, session_id):
            raise auth_error(401, "AUTH_REVOKED")
        email = claims.get("email")
        return VerifiedIdentity(
            self.issuer, subject, email if isinstance(email, str) and len(email) <= 254 else None
        )

    def session_active(self, subject: str, session_id: str) -> bool:
        try:
            with self.engine.begin() as connection:
                connection.execute(text("SET LOCAL statement_timeout = 3000"))
                row = (
                    connection.execute(
                        text(
                            "SELECT s.created_at, s.refreshed_at, s.not_after, "
                            "u.email_confirmed_at, u.banned_until, u.deleted_at "
                            "FROM auth.sessions s JOIN auth.users u ON u.id = s.user_id "
                            "WHERE s.id = CAST(:sid AS uuid) AND s.user_id = CAST(:uid AS uuid)"
                        ),
                        {"sid": session_id, "uid": subject},
                    )
                    .mappings()
                    .first()
                )
        except Exception:
            raise auth_error(503, "AUTH_UNAVAILABLE") from None
        if row is None or row["email_confirmed_at"] is None or row["deleted_at"] is not None:
            return False
        now = datetime.now(UTC)
        if row["banned_until"] is not None and row["banned_until"] > now:
            return False
        if row["not_after"] is not None and row["not_after"] <= now:
            return False
        for limit, stamp in (
            (self.settings.auth_session_max_age_seconds, row["created_at"]),
            (self.settings.auth_session_idle_seconds, row["refreshed_at"] or row["created_at"]),
        ):
            if limit and (stamp is None or (now - stamp).total_seconds() >= limit):
                return False
        return True


def find_or_create_user(session: Session, identity: VerifiedIdentity) -> User:
    query = select(AuthIdentity).where(
        AuthIdentity.issuer == identity.issuer,
        AuthIdentity.subject == identity.subject,
    )
    stored = session.scalar(query)
    if stored is None:
        try:
            with session.begin_nested():
                user = User(id=str(uuid4()), email=identity.email, active=True)
                session.add(user)
                session.flush()
                stored = AuthIdentity(
                    id=str(uuid4()),
                    user_id=user.id,
                    issuer=identity.issuer,
                    subject=identity.subject,
                )
                session.add(stored)
                session.flush()
            session.commit()
        except IntegrityError:
            stored = session.scalar(query)
            if stored is None:
                raise auth_error(503, "AUTH_UNAVAILABLE") from None
    user = session.get(User, stored.user_id)
    if user is None or not user.active:
        raise auth_error(403, "ACCOUNT_UNAVAILABLE")
    return user


def optional_user(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> User | None:
    header = request.headers.get("authorization")
    if header is None:
        return None
    if not request.app.state.settings.auth_enabled:
        raise auth_error(401, "AUTH_DISABLED")
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or len(parts[1]) > 16_384:
        raise auth_error()
    identity = request.app.state.auth_verifier.verify(parts[1])
    return find_or_create_user(session, identity)


def required_user(user: Annotated[User | None, Depends(optional_user)]) -> User:
    if user is None:
        raise auth_error(401, "AUTH_REQUIRED")
    return user
