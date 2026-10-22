from fastapi import APIRouter, status

from app.domains.identity.repository import UserRepository
from app.domains.identity.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.domains.identity.service import IdentityService, create_access_token
from app.interface.api.deps import CurrentUser, SessionDep

router = APIRouter(prefix="/api/v1/auth", tags=["Авторизация"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(payload: RegisterRequest, session: SessionDep):
    service = IdentityService(UserRepository(session))
    return await service.register(
        email=str(payload.email),
        password=payload.password,
    )


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, session: SessionDep) -> TokenResponse:
    service = IdentityService(UserRepository(session))
    user = await service.authenticate(
        email=str(payload.email),
        password=payload.password,
    )
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse)
async def me(current_user: CurrentUser):
    return current_user
