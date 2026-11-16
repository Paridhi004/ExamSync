from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.allocation import Allocation
    from app.models.user import User


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_students"),
        UniqueConstraint("roll_number", name="uq_students_roll_number"),
        UniqueConstraint("user_id", name="uq_students_user_id"),
        Index("ix_students_roll_number", "roll_number"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(Integer, autoincrement=True)
    roll_number: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", name="fk_students_user_id_users", ondelete="RESTRICT"),
        nullable=True,
    )

    user: Mapped[User | None] = relationship(back_populates="student", lazy="select")
    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="student", lazy="select")
    allocations: Mapped[list[Allocation]] = relationship(back_populates="student", lazy="select")


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_subjects"),
        UniqueConstraint("code", name="uq_subjects_code"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(Integer, autoincrement=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="subject", lazy="select")
    exams: Mapped[list[Exam]] = relationship(back_populates="subject", lazy="select")


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_enrollments"),
        UniqueConstraint("student_id", "subject_id", name="uq_enrollments_student_subject"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(Integer, autoincrement=True)
    student_id: Mapped[int] = mapped_column(
        ForeignKey("students.id", name="fk_enrollments_student_id_students", ondelete="RESTRICT"),
        nullable=False,
    )
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", name="fk_enrollments_subject_id_subjects", ondelete="RESTRICT"),
        nullable=False,
    )

    student: Mapped[Student] = relationship(back_populates="enrollments", lazy="select")
    subject: Mapped[Subject] = relationship(back_populates="enrollments", lazy="select")


from app.models.exam import Exam
