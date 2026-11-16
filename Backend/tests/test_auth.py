from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.dependencies import require_role
from app.core.security import create_access_token, hash_password, verify_password
from app.models import User, UserRole
from app.routers.auth import router as auth_router

admin_test_router = APIRouter()


@admin_test_router.get("/test/admin", dependencies=[Depends(require_role(UserRole.ADMIN))])
def admin_only_route() -> dict[str, bool]:
    return {"ok": True}


@pytest.fixture
def test_engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture
def client(test_engine: Engine) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(admin_test_router)

    def override_get_db() -> Iterator[Session]:
        with Session(test_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def create_user(test_engine: Engine, email: str, role: UserRole) -> User:
    with Session(test_engine, expire_on_commit=False) as session:
        user = User(email=email, password_hash=hash_password("correct-password"), role=role)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def test_register_then_login_and_password_is_stored_hashed(
    client: TestClient, test_engine: Engine
) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "student@example.com", "password": "student-password"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "student"
    assert "password_hash" not in response.json()

    with Session(test_engine) as session:
        user = session.query(User).filter_by(email="student@example.com").one()
        assert user.password_hash != "student-password"
        assert verify_password("student-password", user.password_hash)

    login_response = client.post(
        "/auth/login",
        data={"username": "student@example.com", "password": "student-password"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["token_type"] == "bearer"
    assert client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
    ).status_code == 200


def test_wrong_password_returns_401(client: TestClient) -> None:
    client.post(
        "/auth/register",
        json={"email": "student@example.com", "password": "student-password"},
    )

    response = client.post(
        "/auth/login",
        data={"username": "student@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"] == "Incorrect email or password."


def test_missing_token_returns_401(client: TestClient) -> None:
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_tampered_token_returns_401(client: TestClient, test_engine: Engine) -> None:
    user = create_user(test_engine, "student@example.com", UserRole.STUDENT)
    token = create_access_token(user.id, user.role)
    claims = jwt.decode(
        token,
        settings.jwt_secret.get_secret_value(),
        algorithms=[settings.jwt_algorithm],
    )
    tampered_token = jwt.encode(
        claims,
        "incorrect-test-signing-secret-long-enough",
        algorithm=settings.jwt_algorithm,
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_expired_token_returns_401(client: TestClient, test_engine: Engine) -> None:
    user = create_user(test_engine, "student@example.com", UserRole.STUDENT)
    now = datetime.now(timezone.utc)
    expired_token = jwt.encode(
        {
            "sub": str(user.id),
            "role": UserRole.STUDENT.value,
            "iat": now - timedelta(minutes=2),
            "exp": now - timedelta(minutes=1),
        },
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_student_is_forbidden_from_admin_route(client: TestClient, test_engine: Engine) -> None:
    user = create_user(test_engine, "student@example.com", UserRole.STUDENT)
    token = create_access_token(user.id, user.role)

    response = client.get("/test/admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_admin_can_access_admin_route(client: TestClient, test_engine: Engine) -> None:
    user = create_user(test_engine, "admin@example.com", UserRole.ADMIN)
    token = create_access_token(user.id, user.role)

    response = client.get("/test/admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_duplicate_email_returns_409(client: TestClient) -> None:
    payload = {"email": "student@example.com", "password": "student-password"}
    assert client.post("/auth/register", json=payload).status_code == 201

    response = client.post("/auth/register", json=payload)
    assert response.status_code == 409
