from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, PrimaryKeyConstraint, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.exam import Exam, ExamSlot
    from app.models.room import Seat
    from app.models.student import Student


class Allocation(Base):
    __tablename__ = "allocations"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_allocations"),
        UniqueConstraint("slot_id", "student_id", name="uq_alloc_slot_student"),
        UniqueConstraint("slot_id", "seat_id", name="uq_alloc_slot_seat"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(Integer, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(
        ForeignKey("exam_slots.id", name="fk_allocations_slot_id_exam_slots", ondelete="RESTRICT"),
        nullable=False,
    )
    exam_id: Mapped[int] = mapped_column(
        ForeignKey("exams.id", name="fk_allocations_exam_id_exams", ondelete="RESTRICT"),
        nullable=False,
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", name="fk_allocations_student_id_students", ondelete="RESTRICT"),
        nullable=False,
    )
    seat_id: Mapped[int] = mapped_column(
        ForeignKey("seats.id", name="fk_allocations_seat_id_seats", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    slot: Mapped[ExamSlot] = relationship(back_populates="allocations", lazy="select")
    exam: Mapped[Exam] = relationship(back_populates="allocations", lazy="select")
    student: Mapped[Student] = relationship(back_populates="allocations", lazy="select")
    seat: Mapped[Seat] = relationship(back_populates="allocations", lazy="select")
