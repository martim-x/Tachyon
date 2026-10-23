"""Схемы регистрации, авторизации и пользователя."""

from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
)


class RegisterRequest(BaseModel):
    email: EmailStr = Field(
        description="Уникальный email пользователя",
    )
    password: str = Field(
        min_length=8,
        description=("Пароль длиной не менее 8 символов и не более 72 байт UTF-8"),
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "secure-password-123",
            }
        }
    )

    @field_validator("password")
    @classmethod
    def validate_bcrypt_length(
        cls,
        password: str,
    ) -> str:
        if len(password.encode("utf-8")) > 72:
            raise ValueError("Пароль не должен превышать 72 байта")

        return password


class LoginRequest(BaseModel):
    email: EmailStr = Field(
        description="Email зарегистрированного пользователя",
    )
    password: str = Field(
        description="Пароль пользователя",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "user@example.com",
                "password": "secure-password-123",
            }
        }
    )


class UserResponse(BaseModel):
    id: UUID = Field(
        description="Идентификатор пользователя",
    )
    email: EmailStr = Field(
        description="Email пользователя",
    )

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": ("10000000-0000-0000-0000-000000000001"),
                "email": "user@example.com",
            }
        },
    )


class TokenResponse(BaseModel):
    access_token: str = Field(
        description="JWT access-токен",
    )
    token_type: Literal["bearer"] = Field(
        default="bearer",
        description="Схема авторизации",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."),
                "token_type": "bearer",
            }
        }
    )
