from typing import Annotated, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models import (
    Enrollment,
    Exam,
    ExamSlot,
    Room,
    Student,
    Subject,
    User,
    generate_seats_for_room,
)
from app.schemas.resources import (
    EnrollmentCreate,
    EnrollmentOut,
    ExamCreate,
    ExamOut,
    ExamSlotCreate,
    ExamSlotOut,
    RoomCreate,
    RoomOut,
    StudentCreate,
    StudentOut,
    SubjectCreate,
    SubjectOut,
)

router = APIRouter(
    tags=["admin"],
    dependencies=[Depends(require_role("admin"))],
)
DbSession = Annotated[Session, Depends(get_db)]
ModelT = TypeVar("ModelT")


def _commit_new(db: Session, row: ModelT) -> ModelT:
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A record with the supplied unique values already exists.",
        ) from None
    return row


def _require_parent(db: Session, model: type[ModelT], entity_id: int, name: str) -> ModelT:
    parent = db.get(model, entity_id)
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{name} {entity_id} not found.",
        )
    return parent


@router.post("/subjects", response_model=SubjectOut, status_code=status.HTTP_201_CREATED)
def create_subject(payload: SubjectCreate, db: DbSession) -> SubjectOut:
    row = _commit_new(db, Subject(**payload.model_dump()))
    return SubjectOut.model_validate(row, from_attributes=True)


@router.get("/subjects", response_model=list[SubjectOut])
def list_subjects(db: DbSession) -> list[SubjectOut]:
    return [
        SubjectOut.model_validate(row, from_attributes=True)
        for row in db.scalars(select(Subject).order_by(Subject.code))
    ]


@router.post("/students", response_model=StudentOut, status_code=status.HTTP_201_CREATED)
def create_student(payload: StudentCreate, db: DbSession) -> StudentOut:
    if payload.user_id is not None:
        _require_parent(db, User, payload.user_id, "User")
    row = _commit_new(db, Student(**payload.model_dump()))
    return StudentOut.model_validate(row, from_attributes=True)


@router.get("/students", response_model=list[StudentOut])
def list_students(db: DbSession) -> list[StudentOut]:
    return [
        StudentOut.model_validate(row, from_attributes=True)
        for row in db.scalars(select(Student).order_by(Student.roll_number))
    ]


@router.post("/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(payload: RoomCreate, db: DbSession) -> RoomOut:
    room = Room(**payload.model_dump())
    room.seats.extend(generate_seats_for_room(room))
    row = _commit_new(db, room)
    return RoomOut.model_validate(row, from_attributes=True)


@router.get("/rooms", response_model=list[RoomOut])
def list_rooms(db: DbSession) -> list[RoomOut]:
    return [
        RoomOut.model_validate(row, from_attributes=True)
        for row in db.scalars(select(Room).order_by(Room.id))
    ]


@router.post("/slots", response_model=ExamSlotOut, status_code=status.HTTP_201_CREATED)
def create_slot(payload: ExamSlotCreate, db: DbSession) -> ExamSlotOut:
    row = _commit_new(db, ExamSlot(**payload.model_dump()))
    return ExamSlotOut.model_validate(row, from_attributes=True)


@router.get("/slots", response_model=list[ExamSlotOut])
def list_slots(db: DbSession) -> list[ExamSlotOut]:
    return [
        ExamSlotOut.model_validate(row, from_attributes=True)
        for row in db.scalars(
            select(ExamSlot).order_by(ExamSlot.exam_date, ExamSlot.label)
        )
    ]


@router.post("/exams", response_model=ExamOut, status_code=status.HTTP_201_CREATED)
def create_exam(payload: ExamCreate, db: DbSession) -> ExamOut:
    _require_parent(db, Subject, payload.subject_id, "Subject")
    _require_parent(db, ExamSlot, payload.slot_id, "Slot")
    row = _commit_new(db, Exam(**payload.model_dump()))
    return ExamOut.model_validate(row, from_attributes=True)


@router.get("/exams", response_model=list[ExamOut])
def list_exams(db: DbSession) -> list[ExamOut]:
    return [
        ExamOut.model_validate(row, from_attributes=True)
        for row in db.scalars(select(Exam).order_by(Exam.slot_id, Exam.subject_id))
    ]


@router.post(
    "/enrollments",
    response_model=EnrollmentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_enrollment(payload: EnrollmentCreate, db: DbSession) -> EnrollmentOut:
    _require_parent(db, Student, payload.student_id, "Student")
    _require_parent(db, Subject, payload.subject_id, "Subject")
    row = _commit_new(db, Enrollment(**payload.model_dump()))
    return EnrollmentOut.model_validate(row, from_attributes=True)


@router.get("/enrollments", response_model=list[EnrollmentOut])
def list_enrollments(db: DbSession) -> list[EnrollmentOut]:
    return [
        EnrollmentOut.model_validate(row, from_attributes=True)
        for row in db.scalars(
            select(Enrollment).order_by(Enrollment.subject_id, Enrollment.student_id)
        )
    ]


