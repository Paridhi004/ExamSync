from dataclasses import dataclass


@dataclass(frozen=True)
class RoomGrid:
    id: int
    rows: int
    cols: int


@dataclass(frozen=True)
class Assignment:
    student_id: int
    subject_code: str
    room_id: int
    row: int
    col: int


@dataclass(frozen=True)
class AllocationResult:
    assignments: list[Assignment]
    unseated: list[tuple[int, str]]


def allocate(queues: dict[str, list[int]], rooms: list[RoomGrid]) -> AllocationResult:
    """Allocate by room and even-numbered columns using subject round-robin.

    Student order within each subject is preserved, and the round-robin pointer
    continues across rooms. Once only one subject still has students, adjacent
    vertical neighbours may be from that same subject; spacing is always
    preserved by leaving odd-numbered columns empty.
    """
    seen_student_ids: set[int] = set()
    for subject_code, student_ids in queues.items():
        for student_id in student_ids:
            if student_id in seen_student_ids:
                raise ValueError(f"Student id {student_id} appears more than once.")
            seen_student_ids.add(student_id)

    for room in rooms:
        if room.rows < 1 or room.cols < 1:
            raise ValueError(f"Room {room.id} must have at least one row and column.")

    subject_codes = sorted(queues)
    positions = {subject_code: 0 for subject_code in subject_codes}
    assignments: list[Assignment] = []
    rotation_pointer = 0

    for room in rooms:
        for col in range(0, room.cols, 2):
            for row in range(room.rows):
                for offset in range(len(subject_codes)):
                    subject_index = (rotation_pointer + offset) % len(subject_codes)
                    subject_code = subject_codes[subject_index]
                    queue_position = positions[subject_code]
                    if queue_position >= len(queues[subject_code]):
                        continue

                    student_id = queues[subject_code][queue_position]
                    positions[subject_code] += 1
                    rotation_pointer = (subject_index + 1) % len(subject_codes)
                    assignments.append(
                        Assignment(
                            student_id=student_id,
                            subject_code=subject_code,
                            room_id=room.id,
                            row=row,
                            col=col,
                        )
                    )
                    break
                else:
                    return AllocationResult(
                        assignments=assignments,
                        unseated=[
                            (student_id, subject_code)
                            for subject_code in subject_codes
                            for student_id in queues[subject_code][positions[subject_code] :]
                        ],
                    )

    return AllocationResult(
        assignments=assignments,
        unseated=[
            (student_id, subject_code)
            for subject_code in subject_codes
            for student_id in queues[subject_code][positions[subject_code] :]
        ],
    )
