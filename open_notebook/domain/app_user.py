from datetime import datetime
from typing import ClassVar, List, Optional, Type, TypeVar

import bcrypt
from pydantic import field_validator

from open_notebook.database.repository import repo_query
from open_notebook.domain.base import ObjectModel
from open_notebook.exceptions import InvalidInputError

T = TypeVar("T", bound="AppUser")


class AppUser(ObjectModel):
    table_name: ClassVar[str] = "app_user"

    username: str
    email: str
    display_name: Optional[str] = None
    password_hash: Optional[str] = None
    role: str = "user"
    status: str = "pending"
    auth_provider: str = "local"
    last_login: Optional[datetime] = None

    @field_validator("username")
    @classmethod
    def username_not_empty(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise InvalidInputError("Username cannot be empty")
        return v

    @field_validator("email")
    @classmethod
    def email_not_empty(cls, v: str) -> str:
        v = v.strip().lower()
        if not v or "@" not in v:
            raise InvalidInputError("A valid email is required")
        return v

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str) -> str:
        if v not in ("super_admin", "admin", "user"):
            raise InvalidInputError(f"Invalid role: {v}")
        return v

    @field_validator("status")
    @classmethod
    def status_valid(cls, v: str) -> str:
        if v not in ("pending", "active", "deactivated"):
            raise InvalidInputError(f"Invalid status: {v}")
        return v

    @field_validator("auth_provider")
    @classmethod
    def auth_provider_valid(cls, v: str) -> str:
        if v not in ("local", "ldap"):
            raise InvalidInputError(f"Invalid auth_provider: {v}")
        return v

    @field_validator("last_login", mode="before")
    @classmethod
    def parse_last_login(cls, value):
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def is_admin(self) -> bool:
        return self.role in ("admin", "super_admin")

    @property
    def is_super_admin(self) -> bool:
        return self.role == "super_admin"

    def set_password(self, plain_password: str) -> None:
        hashed = bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt())
        self.password_hash = hashed.decode("utf-8")

    def verify_password(self, plain_password: str) -> bool:
        if not self.password_hash:
            return False
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            self.password_hash.encode("utf-8"),
        )

    @classmethod
    async def get_by_username(cls: Type[T], username: str) -> Optional[T]:
        username = username.strip().lower()
        result = await repo_query(
            "SELECT * FROM app_user WHERE username = $username LIMIT 1",
            {"username": username},
        )
        if result:
            return cls(**result[0])
        return None

    @classmethod
    async def get_by_email(cls: Type[T], email: str) -> Optional[T]:
        email = email.strip().lower()
        result = await repo_query(
            "SELECT * FROM app_user WHERE email = $email LIMIT 1",
            {"email": email},
        )
        if result:
            return cls(**result[0])
        return None

    @classmethod
    async def get_all_users(cls: Type[T], status: Optional[str] = None) -> List[T]:
        if status:
            result = await repo_query(
                "SELECT * FROM app_user WHERE status = $status ORDER BY username",
                {"status": status},
            )
        else:
            result = await repo_query(
                "SELECT * FROM app_user ORDER BY username"
            )
        return [cls(**row) for row in result]

    def to_public_dict(self) -> dict:
        """Return user data safe for API responses (no password_hash)."""
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "display_name": self.display_name,
            "role": self.role,
            "status": self.status,
            "auth_provider": self.auth_provider,
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "created": self.created.isoformat() if self.created else None,
            "updated": self.updated.isoformat() if self.updated else None,
        }
