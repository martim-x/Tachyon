"""HTTP API регистрации и JWT-авторизации."""

from fastapi import APIRouter, status

from app.domains.identity.repository import UserRepository
from app.domains.identity.schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.domains.identity.service import (
    IdentityService,
    create_access_token,
)
from app.interface.api.deps import CurrentUser, SessionDep
from app.interface.api.schemas import error_responses

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["Авторизация"],
)


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Зарегистрировать пользователя",
    description=(
        "Создаёт пользователя с уникальным email. Пароль сохраняется только как bcrypt-хеш."
    ),
    responses=error_responses(409, 422),
)
async def register(
    payload: RegisterRequest,
    session: SessionDep,
):
    service = IdentityService(UserRepository(session))

    return await service.register(
        email=str(payload.email),
        password=payload.password,
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Войти в систему",
    description=("Проверяет email и пароль и возвращает JWT access-токен."),
    responses=error_responses(401, 422),
)
async def login(
    payload: LoginRequest,
    session: SessionDep,
) -> TokenResponse:
    service = IdentityService(UserRepository(session))
    user = await service.authenticate(
        email=str(payload.email),
        password=payload.password,
    )

    return TokenResponse(access_token=create_access_token(user.id))


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Получить текущего пользователя",
    description=("Возвращает пользователя из Bearer JWT."),
    responses=error_responses(401),
)
async def me(
    current_user: CurrentUser,
):
    return current_user
