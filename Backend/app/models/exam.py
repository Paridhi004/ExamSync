from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Date,
    ForeignKey,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.allocation import Allocation
    from app.models.student import Subject


class ExamSlot(Base):
    __tablename__ = "exam_slots"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_exam_slots"),
        UniqueConstraint("exam_date", "label", name="uq_exam_slots_date_label"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(Integer, autoincrement=True)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)

    exams: Mapped[list[Exam]] = relationship(back_populates="slot", lazy="select")
    allocations: Mapped[list[Allocation]] = relationship(back_populates="slot", lazy="select")


class Exam(Base):
    __tablename__ = "exams"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_exams"),
        UniqueConstraint("subject_id", "slot_id", name="uq_exams_subject_slot"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(Integer, autoincrement=True)
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", name="fk_exams_subject_id_subjects", ondelete="RESTRICT"),
        nullable=False,
    )
    slot_id: Mapped[int] = mapped_column(
        ForeignKey("exam_slots.id", name="fk_exams_slot_id_exam_slots", ondelete="RESTRICT"),
        nullable=False,
    )

    subject: Mapped[Subject] = relationship(back_populates="exams", lazy="select")
    slot: Mapped[ExamSlot] = relationship(back_populates="exams", lazy="select")
    allocations: Mapped[list[Allocation]] = relationship(back_populates="exam", lazy="select")


from app.models.allocation import Allocation
