import pytest

from app.allocation.engine import AllocationResult, Assignment, RoomGrid, allocate


def test_more_students_than_seats_returns_remaining_in_subject_order() -> None:
    result = allocate(
        {"BIO": [10, 11], "ALG": [20, 21, 22]},
        [RoomGrid(id=1, rows=1, cols=4)],
    )

    assert result.assignments == [
        Assignment(20, "ALG", 1, 0, 0),
        Assignment(10, "BIO", 1, 0, 2),
    ]
    assert result.unseated == [(21, "ALG"), (22, "ALG"), (11, "BIO")]


def test_single_subject_only_preserves_queue_order() -> None:
    result = allocate({"MATH": [4, 5, 6]}, [RoomGrid(id=3, rows=2, cols=1)])

    assert result.assignments == [
        Assignment(4, "MATH", 3, 0, 0),
        Assignment(5, "MATH", 3, 1, 0),
    ]
    assert result.unseated == [(6, "MATH")]


def test_uneven_rooms_keep_column_order_and_rotation_pointer() -> None:
    result = allocate(
        {"B": [10, 11, 12], "A": [1, 2, 3]},
        [
            RoomGrid(id=1, rows=1, cols=1),
            RoomGrid(id=2, rows=1, cols=3),
        ],
    )

    assert result.assignments == [
        Assignment(1, "A", 1, 0, 0),
        Assignment(10, "B", 2, 0, 0),
        Assignment(2, "A", 2, 0, 2),
    ]
    assert result.unseated == [(3, "A"), (11, "B"), (12, "B")]


def test_empty_queues_and_empty_rooms() -> None:
    assert allocate({}, [RoomGrid(id=1, rows=2, cols=2)]) == AllocationResult([], [])
    assert allocate({"A": [], "B": []}, []) == AllocationResult([], [])
    assert allocate({"A": [1]}, []) == AllocationResult([], [(1, "A")])


def test_allocation_is_deterministic() -> None:
    queues = {"Z": [5, 6, 7], "A": [1, 2, 3]}
    rooms = [RoomGrid(id=2, rows=2, cols=4), RoomGrid(id=3, rows=1, cols=3)]

    assert allocate(queues, rooms) == allocate(queues, rooms)


def test_no_two_assignments_use_adjacent_columns_in_same_row() -> None:
    result = allocate(
        {"A": list(range(20)), "B": list(range(20, 40))},
        [RoomGrid(id=1, rows=3, cols=5)],
    )

    coordinates = {(a.room_id, a.row, a.col) for a in result.assignments}
    assert all(assignment.col % 2 == 0 for assignment in result.assignments)
    assert all(
        (room_id, row, col + 1) not in coordinates
        for room_id, row, col in coordinates
    )


def test_vertical_neighbours_alternate_while_multiple_subjects_remain() -> None:
    result = allocate(
        {"B": list(range(20, 30)), "A": list(range(10, 20))},
        [RoomGrid(id=1, rows=5, cols=1)],
    )

    by_row = {assignment.row: assignment for assignment in result.assignments}
    assert len(by_row) == 5
    assert all(by_row[row].subject_code != by_row[row + 1].subject_code for row in range(4))


def test_every_student_is_assigned_or_unseated_exactly_once() -> None:
    queues = {"B": [3, 4, 5], "A": [1, 2], "C": []}
    result = allocate(queues, [RoomGrid(id=1, rows=2, cols=2)])

    accounted_for = [
        assignment.student_id for assignment in result.assignments
    ] + [student_id for student_id, _ in result.unseated]
    expected = [student_id for queue in queues.values() for student_id in queue]
    assert sorted(accounted_for) == sorted(expected)
    assert len(accounted_for) == len(set(accounted_for))


def test_duplicate_student_id_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Student id 7"):
        allocate({"A": [7], "B": [8, 7]}, [RoomGrid(id=1, rows=1, cols=1)])


@pytest.mark.parametrize(
    "room",
    [RoomGrid(id=1, rows=0, cols=1), RoomGrid(id=1, rows=1, cols=0)],
)
def test_invalid_room_dimensions_raise_value_error(room: RoomGrid) -> None:
    with pytest.raises(ValueError, match="at least one row and column"):
        allocate({}, [room])
