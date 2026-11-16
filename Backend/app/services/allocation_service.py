from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.allocation.engine import AllocationResult, Assignment, RoomGrid, allocate
from app.models import (
    Allocation,
    Enrollment,
    Exam,
    ExamSlot,
    Room,
    Seat,
    Student,
    Subject,
)


class SlotNotFoundError(Exception):
    pass


class RoomNotFoundError(Exception):
    def __init__(self, room_ids: Sequence[int]) -> None:
        self.room_ids = tuple(sorted(room_ids))
        super().__init__(f"Rooms not found: {', '.join(map(str, self.room_ids))}")


class EnrollmentClashError(Exception):
    def __init__(self, student_ids: Sequence[int]) -> None:
        self.student_ids = tuple(sorted(student_ids))
        super().__init__(f"Students enrolled in multiple exams in this slot: {self.student_ids}")


def _slot_roster(
    db: Session,
    slot_id: int,
) -> tuple[dict[str, list[int]], dict[str, int], dict[int, list[str]]]:
    exam_subject_rows = db.execute(
        select(Exam.id, Subject.id, Subject.code)
        .join(Subject, Subject.id == Exam.subject_id)
        .where(Exam.slot_id == slot_id)
        .order_by(Subject.code, Exam.id)
    ).all()
    exam_ids_by_code = {subject_code: exam_id for exam_id, _, subject_code in exam_subject_rows}
    subject_ids = [subject_id for _, subject_id, _ in exam_subject_rows]
    queues: dict[str, list[int]] = {code: [] for code in sorted(exam_ids_by_code)}
    student_subjects: dict[int, list[str]] = defaultdict(list)

    if subject_ids:
        enrollment_rows = db.execute(
            select(Subject.code, Student.id, Student.roll_number)
            .select_from(Enrollment)
            .join(Student, Student.id == Enrollment.student_id)
            .join(Subject, Subject.id == Enrollment.subject_id)
            .where(Enrollment.subject_id.in_(subject_ids))
            .order_by(Subject.code, Student.roll_number, Student.id)
        ).all()
        for subject_code, student_id, _ in enrollment_rows:
            queues[subject_code].append(student_id)
            student_subjects[student_id].append(subject_code)

    return queues, exam_ids_by_code, student_subjects


def allocate_slot(
    db: Session,
    slot_id: int,
    room_ids: list[int] | None = None,
) -> AllocationResult:
    try:
        slot = db.scalar(
            select(ExamSlot)
            .where(ExamSlot.id == slot_id)
            .with_for_update()
        )
        if slot is None:
            raise SlotNotFoundError(f"Exam slot {slot_id} not found.")

        queues, exam_ids_by_code, student_subjects = _slot_roster(db, slot_id)
        clashes = [
            student_id
            for student_id, subject_codes in student_subjects.items()
            if len(subject_codes) > 1
        ]
        if clashes:
            raise EnrollmentClashError(clashes)

        room_query = select(Room).order_by(Room.id)
        if room_ids is not None:
            room_query = room_query.where(Room.id.in_(room_ids))
        rooms = list(db.scalars(room_query))
        if room_ids is not None:
            missing_room_ids = set(room_ids) - {room.id for room in rooms}
            if missing_room_ids:
                raise RoomNotFoundError(missing_room_ids)

        room_grids = [RoomGrid(room.id, room.num_rows, room.num_cols) for room in rooms]
        result = allocate(queues, room_grids)

        room_ids_in_order = [room.id for room in rooms]
        seat_rows = (
            db.scalars(select(Seat).where(Seat.room_id.in_(room_ids_in_order))).all()
            if room_ids_in_order
            else []
        )
        seat_ids = {(seat.room_id, seat.row, seat.col): seat.id for seat in seat_rows}
        new_allocations: list[Allocation] = []
        for assignment in result.assignments:
            seat_id = seat_ids.get((assignment.room_id, assignment.row, assignment.col))
            exam_id = exam_ids_by_code.get(assignment.subject_code)
            if seat_id is None:
                raise ValueError(
                    f"Seat missing for room {assignment.room_id}, "
                    f"row {assignment.row}, column {assignment.col}."
                )
            if exam_id is None:
                raise ValueError(f"No exam found for subject {assignment.subject_code}.")
            new_allocations.append(
                Allocation(
                    slot_id=slot_id,
                    exam_id=exam_id,
                    student_id=assignment.student_id,
                    seat_id=seat_id,
                )
            )

        db.execute(delete(Allocation).where(Allocation.slot_id == slot_id))
        db.add_all(new_allocations)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def get_slot_allocations(db: Session, slot_id: int) -> AllocationResult:
    if db.scalar(select(ExamSlot.id).where(ExamSlot.id == slot_id)) is None:
        raise SlotNotFoundError(f"Exam slot {slot_id} not found.")

    queues, _, _ = _slot_roster(db, slot_id)
    allocation_rows = db.execute(
        select(
            Allocation.student_id,
            Subject.code,
            Seat.room_id,
            Seat.row,
            Seat.col,
        )
        .join(Exam, Exam.id == Allocation.exam_id)
        .join(Subject, Subject.id == Exam.subject_id)
        .join(Seat, Seat.id == Allocation.seat_id)
        .where(Allocation.slot_id == slot_id)
        .order_by(Seat.room_id, Seat.col, Seat.row)
    ).all()
    assignments = [
        Assignment(
            student_id=student_id,
            subject_code=subject_code,
            room_id=room_id,
            row=row,
            col=col,
        )
        for student_id, subject_code, room_id, row, col in allocation_rows
    ]
    allocated_student_ids = {assignment.student_id for assignment in assignments}
    unseated = [
        (student_id, subject_code)
        for subject_code in sorted(queues)
        for student_id in queues[subject_code]
        if student_id not in allocated_student_ids
    ]
    return AllocationResult(assignments=assignments, unseated=unseated)
