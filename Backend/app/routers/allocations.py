from collections import defaultdict
from typing import Annotated
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.allocation.engine import Assignment
from app.core.database import get_db
from app.core.dependencies import require_role
from app.schemas.resources import (
    AllocationRequest,
    AllocationResultOut,
    AssignmentOut,
    RoomAssignmentsOut,
    UnseatedStudentOut,
)
from app.services.allocation_service import (
    EnrollmentClashError,
    RoomNotFoundError,
    SlotNotFoundError,
    allocate_slot,
    get_slot_allocations,
)

router = APIRouter(
    tags=["allocations"],
    dependencies=[Depends(require_role("admin"))],
)
DbSession = Annotated[Session, Depends(get_db)]


def _result_response(
    assignments: list[Assignment],
    unseated: list[tuple[int, str]],
) -> AllocationResultOut:
    grouped: dict[int, list[AssignmentOut]] = defaultdict(list)
    for assignment in assignments:
        grouped[assignment.room_id].append(
            AssignmentOut(
                student_id=assignment.student_id,
                subject_code=assignment.subject_code,
                room_id=assignment.room_id,
                row=assignment.row,
                col=assignment.col,
            )
        )
    return AllocationResultOut(
        assignments_by_room=[
            RoomAssignmentsOut(room_id=room_id, assignments=room_assignments)
            for room_id, room_assignments in sorted(grouped.items())
        ],
        unseated=[
            UnseatedStudentOut(student_id=student_id, subject_code=subject_code)
            for student_id, subject_code in unseated
        ],
    )


def _raise_http_error(error: Exception) -> NoReturn:
    if isinstance(error, SlotNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    if isinstance(error, RoomNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"message": str(error), "room_ids": list(error.room_ids)},
        ) from error
    if isinstance(error, EnrollmentClashError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Students are enrolled in more than one exam in this slot.",
                "student_ids": list(error.student_ids),
            },
        ) from error
    if isinstance(error, ValueError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    raise error


@router.post("/slots/{slot_id}/allocate", response_model=AllocationResultOut)
def post_allocate_slot(
    slot_id: int,
    db: DbSession,
    payload: AllocationRequest | None = None,
) -> AllocationResultOut:
    try:
        result = allocate_slot(db, slot_id, payload.room_ids if payload is not None else None)
    except (SlotNotFoundError, RoomNotFoundError, EnrollmentClashError, ValueError) as error:
        _raise_http_error(error)
        raise
    return _result_response(result.assignments, result.unseated)


@router.get("/slots/{slot_id}/allocations", response_model=AllocationResultOut)
def read_slot_allocations(slot_id: int, db: DbSession) -> AllocationResultOut:
    try:
        result = get_slot_allocations(db, slot_id)
    except SlotNotFoundError as error:
        _raise_http_error(error)
        raise
    return _result_response(result.assignments, result.unseated)
