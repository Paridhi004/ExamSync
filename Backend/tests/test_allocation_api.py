from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.models import (
    Allocation,
    Enrollment,
    Exam,
    ExamSlot,
    Room,
    Seat,
    Student,
    Subject,
    User,
    UserRole,
    generate_seats_for_room,
)
from app.routers.admin import router as admin_router
from app.routers.allocations import router as allocations_router
from app.routers.auth import router as auth_router


@dataclass(frozen=True)
class SeedData:
    slot_id: int
    student_ids: tuple[int, ...]
    subject_ids: tuple[int, int]
    exam_ids: tuple[int, int]
    room_id: int


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
    app.include_router(admin_router)
    app.include_router(allocations_router)

    def override_get_db() -> Iterator[Session]:
        with Session(test_engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def admin_token(test_engine: Engine) -> str:
    with Session(test_engine) as session:
        admin = User(
            email="allocation-admin@example.com",
            password_hash=hash_password("test-password"),
            role=UserRole.ADMIN,
        )
        session.add(admin)
        session.commit()
        return create_access_token(admin.id, admin.role)


def seed_data(
    test_engine: Engine,
    *,
    room_rows: int = 2,
    room_cols: int = 4,
    clash: bool = False,
) -> SeedData:
    with Session(test_engine) as session:
        subjects = [
            Subject(code="ALG", name="Algebra"),
            Subject(code="BIO", name="Biology"),
        ]
        students = [
            Student(roll_number="R001", name="Student 1"),
            Student(roll_number="R002", name="Student 2"),
            Student(roll_number="R003", name="Student 3"),
        ]
        slot = ExamSlot(exam_date=date(2031, 4, 5), label="Morning")
        room = Room(name="Test Room", num_rows=room_rows, num_cols=room_cols)
        room.seats.extend(generate_seats_for_room(room))
        session.add_all([*subjects, *students, slot, room])
        session.flush()

        exams = [
            Exam(subject_id=subjects[0].id, slot_id=slot.id),
            Exam(subject_id=subjects[1].id, slot_id=slot.id),
        ]
        enrollments = [
            Enrollment(student_id=students[0].id, subject_id=subjects[0].id),
            Enrollment(student_id=students[1].id, subject_id=subjects[0].id),
            Enrollment(student_id=students[2].id, subject_id=subjects[1].id),
        ]
        if clash:
            enrollments.append(
                Enrollment(student_id=students[0].id, subject_id=subjects[1].id)
            )
        session.add_all([*exams, *enrollments])
        session.commit()

        return SeedData(
            slot_id=slot.id,
            student_ids=tuple(student.id for student in students),
            subject_ids=(subjects[0].id, subjects[1].id),
            exam_ids=(exams[0].id, exams[1].id),
            room_id=room.id,
        )


def _admin_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _allocation_student_ids(response_json: dict[str, object]) -> list[int]:
    room_groups = response_json["assignments_by_room"]
    assigned = [
        assignment["student_id"]
        for room_group in room_groups
        for assignment in room_group["assignments"]
    ]
    unseated = [student["student_id"] for student in response_json["unseated"]]
    return assigned + unseated


def test_allocate_happy_path_accounts_for_every_enrolled_student_once(
    client: TestClient,
    test_engine: Engine,
    admin_token: str,
) -> None:
    seed = seed_data(test_engine)

    response = client.post(
        f"/slots/{seed.slot_id}/allocate",
        headers=_admin_headers(admin_token),
    )

    assert response.status_code == 200
    accounted_for = _allocation_student_ids(response.json())
    assert sorted(accounted_for) == sorted(seed.student_ids)
    assert len(accounted_for) == len(set(accounted_for))


def test_not_enough_seats_returns_remaining_students_unseated(
    client: TestClient,
    test_engine: Engine,
    admin_token: str,
) -> None:
    seed = seed_data(test_engine, room_rows=1, room_cols=2)

    response = client.post(
        f"/slots/{seed.slot_id}/allocate",
        headers=_admin_headers(admin_token),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(_allocation_student_ids(body)) == len(seed.student_ids)
    assert len(body["unseated"]) == 2
    assert sum(len(group["assignments"]) for group in body["assignments_by_room"]) == 1


def test_reallocation_replaces_existing_allocation(
    client: TestClient,
    test_engine: Engine,
    admin_token: str,
) -> None:
    seed = seed_data(test_engine, room_rows=1, room_cols=2)
    url = f"/slots/{seed.slot_id}/allocate"
    headers = _admin_headers(admin_token)
    assert client.post(url, headers=headers).status_code == 200

    with Session(test_engine) as session:
        assert session.scalar(
            select(func.count()).select_from(Allocation).where(Allocation.slot_id == seed.slot_id)
        ) == 1

    response = client.post(url, json={"room_ids": []}, headers=headers)
    assert response.status_code == 200
    assert response.json()["assignments_by_room"] == []
    assert len(response.json()["unseated"]) == len(seed.student_ids)
    with Session(test_engine) as session:
        assert session.scalar(
            select(func.count()).select_from(Allocation).where(Allocation.slot_id == seed.slot_id)
        ) == 0


def test_enrollment_clash_returns_409_and_preserves_existing_rows(
    client: TestClient,
    test_engine: Engine,
    admin_token: str,
) -> None:
    seed = seed_data(test_engine, clash=True)
    with Session(test_engine) as session:
        first_seat_id = session.scalar(
            select(Seat.id)
            .where(Seat.room_id == seed.room_id)
            .limit(1)
        )
        existing = Allocation(
            slot_id=seed.slot_id,
            exam_id=seed.exam_ids[0],
            student_id=seed.student_ids[0],
            seat_id=first_seat_id,
        )
        session.add(existing)
        session.commit()
        existing_id = existing.id

    response = client.post(
        f"/slots/{seed.slot_id}/allocate",
        headers=_admin_headers(admin_token),
    )

    assert response.status_code == 409
    assert response.json()["detail"]["student_ids"] == [seed.student_ids[0]]
    with Session(test_engine) as session:
        rows = list(session.scalars(select(Allocation).where(Allocation.slot_id == seed.slot_id)))
        assert [row.id for row in rows] == [existing_id]


def test_student_token_is_forbidden(
    client: TestClient,
    test_engine: Engine,
) -> None:
    seed = seed_data(test_engine)
    with Session(test_engine) as session:
        student_user = User(
            email="allocation-student@example.com",
            password_hash=hash_password("test-password"),
            role=UserRole.STUDENT,
        )
        session.add(student_user)
        session.commit()
        token = create_access_token(student_user.id, student_user.role)

    response = client.post(
        f"/slots/{seed.slot_id}/allocate",
        headers=_admin_headers(token),
    )
    assert response.status_code == 403


def test_unknown_slot_returns_404(
    client: TestClient,
    admin_token: str,
) -> None:
    response = client.post("/slots/99999/allocate", headers=_admin_headers(admin_token))
    assert response.status_code == 404


def test_mid_save_failure_rolls_back_allocation_inserts(
    client: TestClient,
    test_engine: Engine,
    admin_token: str,
) -> None:
    seed = seed_data(test_engine)

    def fail_allocation_insert(*event_args: object) -> None:
        statement = event_args[2]
        if isinstance(statement, str) and statement.lstrip().upper().startswith(
            "INSERT INTO ALLOCATIONS"
        ):
            raise RuntimeError("forced allocation insert failure")

    event.listen(test_engine, "before_cursor_execute", fail_allocation_insert)
    try:
        response = client.post(
            f"/slots/{seed.slot_id}/allocate",
            headers=_admin_headers(admin_token),
        )
    finally:
        event.remove(test_engine, "before_cursor_execute", fail_allocation_insert)

    assert response.status_code == 500
    with Session(test_engine) as session:
        assert session.scalar(
            select(func.count()).select_from(Allocation).where(Allocation.slot_id == seed.slot_id)
        ) == 0


def test_get_allocations_includes_unseated_enrolled_students(
    client: TestClient,
    test_engine: Engine,
    admin_token: str,
) -> None:
    seed = seed_data(test_engine, room_rows=1, room_cols=2)
    headers = _admin_headers(admin_token)
    assert client.post(f"/slots/{seed.slot_id}/allocate", headers=headers).status_code == 200

    response = client.get(f"/slots/{seed.slot_id}/allocations", headers=headers)
    assert response.status_code == 200
    assert len(_allocation_student_ids(response.json())) == len(seed.student_ids)
    assert len(response.json()["unseated"]) == 2


def test_admin_resource_endpoints_create_lists_and_generate_room_seats(
    client: TestClient,
    test_engine: Engine,
    admin_token: str,
) -> None:
    headers = _admin_headers(admin_token)
    subject_response = client.post(
        "/subjects",
        json={"code": "API-SUB", "name": "API Subject"},
        headers=headers,
    )
    assert subject_response.status_code == 201
    subject_id = subject_response.json()["id"]
    assert client.get("/subjects", headers=headers).json()[0]["code"] == "API-SUB"

    student_response = client.post(
        "/students",
        json={"roll_number": "API-001", "name": "API Student"},
        headers=headers,
    )
    assert student_response.status_code == 201
    student_id = student_response.json()["id"]

    room_response = client.post(
        "/rooms",
        json={"name": "API Room", "num_rows": 2, "num_cols": 3},
        headers=headers,
    )
    assert room_response.status_code == 201
    room_id = room_response.json()["id"]
    with Session(test_engine) as session:
        assert session.scalar(
            select(func.count()).select_from(Seat).where(Seat.room_id == room_id)
        ) == 6

    slot_response = client.post(
        "/slots",
        json={"exam_date": "2032-01-02", "label": "Morning"},
        headers=headers,
    )
    assert slot_response.status_code == 201
    slot_id = slot_response.json()["id"]

    exam_response = client.post(
        "/exams",
        json={"subject_id": subject_id, "slot_id": slot_id},
        headers=headers,
    )
    assert exam_response.status_code == 201
    enrollment_response = client.post(
        "/enrollments",
        json={"student_id": student_id, "subject_id": subject_id},
        headers=headers,
    )
    assert enrollment_response.status_code == 201

    assert len(client.get("/students", headers=headers).json()) == 1
    assert len(client.get("/rooms", headers=headers).json()) == 1
    assert len(client.get("/slots", headers=headers).json()) == 1
    assert len(client.get("/exams", headers=headers).json()) == 1
    assert len(client.get("/enrollments", headers=headers).json()) == 1


def test_missing_parent_on_create_returns_404(
    client: TestClient,
    admin_token: str,
) -> None:
    response = client.post(
        "/exams",
        json={"subject_id": 12345, "slot_id": 67890},
        headers=_admin_headers(admin_token),
    )
    assert response.status_code == 404
