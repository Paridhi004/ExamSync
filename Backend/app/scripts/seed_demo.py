from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import Base, SessionLocal, engine
from app.models import Enrollment, Exam, ExamSlot, Room, Student, Subject, generate_seats_for_room


def _get_or_create_subject(session: Session, code: str, name: str) -> Subject:
    subject = session.scalar(select(Subject).where(Subject.code == code))
    if subject is None:
        subject = Subject(code=code, name=name)
        session.add(subject)
        session.flush()
    return subject


def _get_or_create_student(session: Session, roll_number: str, name: str) -> Student:
    student = session.scalar(select(Student).where(Student.roll_number == roll_number))
    if student is None:
        student = Student(roll_number=roll_number, name=name)
        session.add(student)
        session.flush()
    return student


def _get_or_create_room(session: Session, name: str, rows: int, cols: int) -> Room:
    room = session.scalar(select(Room).where(Room.name == name))
    if room is None:
        room = Room(name=name, num_rows=rows, num_cols=cols)
        room.seats.extend(generate_seats_for_room(room))
        session.add(room)
        session.flush()
    return room


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        try:
            subjects = [
                _get_or_create_subject(session, "DEMO-MATH", "Demo Mathematics"),
                _get_or_create_subject(session, "DEMO-PHY", "Demo Physics"),
            ]
            students = [
                _get_or_create_student(session, f"DEMO-{index:03}", f"Demo Student {index}")
                for index in range(1, 7)
            ]
            for subject, enrolled_students in (
                (subjects[0], students[:3]),
                (subjects[1], students[3:]),
            ):
                for student in enrolled_students:
                    enrollment = session.scalar(
                        select(Enrollment).where(
                            Enrollment.student_id == student.id,
                            Enrollment.subject_id == subject.id,
                        )
                    )
                    if enrollment is None:
                        session.add(Enrollment(student_id=student.id, subject_id=subject.id))

            room = _get_or_create_room(session, "Demo Room", rows=2, cols=4)
            slot_date = date.today()
            slot = session.scalar(
                select(ExamSlot).where(
                    ExamSlot.exam_date == slot_date,
                    ExamSlot.label == "Demo Morning",
                )
            )
            if slot is None:
                slot = ExamSlot(exam_date=slot_date, label="Demo Morning")
                session.add(slot)
                session.flush()
            for subject in subjects:
                exam = session.scalar(
                    select(Exam).where(
                        Exam.subject_id == subject.id,
                        Exam.slot_id == slot.id,
                    )
                )
                if exam is None:
                    session.add(Exam(subject_id=subject.id, slot_id=slot.id))

            session.commit()
            print(
                f"Demo data ready: slot_id={slot.id}, room_id={room.id}. "
                "Use POST /slots/{slot_id}/allocate in Swagger."
            )
        except Exception:
            session.rollback()
            raise


if __name__ == "__main__":
    main()
