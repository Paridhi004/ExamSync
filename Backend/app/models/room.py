from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
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


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_rooms"),
        UniqueConstraint("name", name="uq_rooms_name"),
        CheckConstraint("num_rows > 0", name="ck_rooms_num_rows_positive"),
        CheckConstraint("num_cols > 0", name="ck_rooms_num_cols_positive"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(Integer, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    num_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    num_cols: Mapped[int] = mapped_column(Integer, nullable=False)

    seats: Mapped[list[Seat]] = relationship(
        back_populates="room",
        lazy="select",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Seat(Base):
    __tablename__ = "seats"
    __table_args__ = (
        PrimaryKeyConstraint("id", name="pk_seats"),
        UniqueConstraint("room_id", "row", "col", name="uq_seat_room_row_col"),
        CheckConstraint("`row` >= 0", name="ck_seats_row_nonnegative"),
        CheckConstraint("`col` >= 0", name="ck_seats_col_nonnegative"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},
    )

    id: Mapped[int] = mapped_column(Integer, autoincrement=True)
    room_id: Mapped[int] = mapped_column(
        ForeignKey("rooms.id", name="fk_seats_room_id_rooms", ondelete="CASCADE"),
        nullable=False,
    )
    row: Mapped[int] = mapped_column(Integer, nullable=False)
    col: Mapped[int] = mapped_column(Integer, nullable=False)

    room: Mapped[Room] = relationship(back_populates="seats", lazy="select")
    allocations: Mapped[list[Allocation]] = relationship(back_populates="seat", lazy="select")


def generate_seats_for_room(room: Room) -> list[Seat]:
    return [
        Seat(room=room, row=row_index, col=col_index)
        for row_index in range(room.num_rows)
        for col_index in range(room.num_cols)
    ]
