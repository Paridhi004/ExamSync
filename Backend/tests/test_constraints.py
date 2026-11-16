import os
from collections.abc import Iterator
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import Allocation, Exam, ExamSlot, Room, Seat, Student, Subject


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated MySQL test database.")

    engine = create_engine(database_url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine: Engine) -> Iterator[Session]:
    connection = test_engine.connect()
    transaction = connection.begin()
    with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
        yield session
    transaction.rollback()
    connection.close()


def _seed_allocation_data(
    session: Session,
) -> tuple[ExamSlot, Exam, list[Student], list[Seat]]:
    suffix = uuid4().hex
    slot = ExamSlot(exam_date=date(2030, 1, 1), label=f"Morning-{suffix}")
    subject = Subject(code=f"SUB-{suffix}", name="Test subject")
    students = [
        Student(roll_number=f"ROLL-{suffix}-{index}", name=f"Student {index}")
        for index in range(2)
    ]
    room = Room(name=f"Room-{suffix}", num_rows=1, num_cols=2)
    seats = [Seat(row=0, col=index) for index in range(2)]
    room.seats.extend(seats)
    exam = Exam(subject=subject, slot=slot)

    session.add_all([slot, subject, *students, room, exam])
    session.commit()
    return slot, exam, students, seats


def test_duplicate_slot_seat_allocation_raises_integrity_error(db_session: Session) -> None:
    slot, exam, students, seats = _seed_allocation_data(db_session)
    db_session.add_all(
        [
            Allocation(slot=slot, exam=exam, student=students[0], seat=seats[0]),
            Allocation(slot=slot, exam=exam, student=students[1], seat=seats[0]),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_duplicate_slot_student_allocation_raises_integrity_error(db_session: Session) -> None:
    slot, exam, students, seats = _seed_allocation_data(db_session)
    db_session.add_all(
        [
            Allocation(slot=slot, exam=exam, student=students[0], seat=seats[0]),
            Allocation(slot=slot, exam=exam, student=students[0], seat=seats[1]),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()


def test_duplicate_room_row_col_seat_raises_integrity_error(db_session: Session) -> None:
    suffix = uuid4().hex
    room = Room(name=f"Room-{suffix}", num_rows=1, num_cols=1)
    db_session.add(room)
    db_session.flush()
    db_session.add_all(
        [
            Seat(room=room, row=0, col=0),
            Seat(room=room, row=0, col=0),
        ]
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
