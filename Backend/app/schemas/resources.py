from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class SubjectCreate(BaseModel):
    code: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=255)


class SubjectOut(SubjectCreate):
    id: int


class StudentCreate(BaseModel):
    roll_number: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=255)
    user_id: int | None = None


class StudentOut(StudentCreate):
    id: int


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    num_rows: int = Field(gt=0)
    num_cols: int = Field(gt=0)


class RoomOut(RoomCreate):
    id: int


class ExamSlotCreate(BaseModel):
    exam_date: date
    label: str = Field(min_length=1, max_length=60)


class ExamSlotOut(ExamSlotCreate):
    id: int


class ExamCreate(BaseModel):
    subject_id: int
    slot_id: int


class ExamOut(ExamCreate):
    id: int


class EnrollmentCreate(BaseModel):
    student_id: int
    subject_id: int


class EnrollmentOut(EnrollmentCreate):
    id: int


class AssignmentOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    student_id: int
    subject_code: str
    room_id: int
    row: int
    col: int


class RoomAssignmentsOut(BaseModel):
    room_id: int
    assignments: list[AssignmentOut]


class UnseatedStudentOut(BaseModel):
    student_id: int
    subject_code: str


class AllocationResultOut(BaseModel):
    assignments_by_room: list[RoomAssignmentsOut]
    unseated: list[UnseatedStudentOut]


class AllocationRequest(BaseModel):
    room_ids: list[int] | None = None
