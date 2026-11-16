# ExamSync Seating Allocation

ExamSync is a FastAPI backend that manages exams, student enrollments, rooms, and exam-seat assignments.
Its deterministic seating engine is separate from the database, and allocation runs are saved transactionally.

**Stack:** Python · FastAPI · SQLAlchemy 2 · MySQL 8 · PyJWT · bcrypt · pytest

[![CI](https://github.com/<USER>/<REPO>/actions/workflows/ci.yml/badge.svg)](https://github.com/<USER>/<REPO>/actions/workflows/ci.yml)

## How it seats students

The demo seeder creates two subjects, three students per subject, one 2-row by 4-column room, and a slot with an exam for each subject. Running that seeded roster through the allocation engine produces:

```text
Room Demo Room (2 rows x 4 columns)
      col 0 | col 1 | col 2 | col 3
row 0: DEMO-MATH DEMO-001 | EMPTY | DEMO-MATH DEMO-002 | EMPTY
row 1: DEMO-PHY DEMO-004 | EMPTY | DEMO-PHY DEMO-005 | EMPTY
Unseated: [('DEMO-MATH', 'DEMO-003'), ('DEMO-PHY', 'DEMO-006')]
```

Read seats in allocation order: down each usable column, then move right; odd-numbered columns stay empty. Subjects rotate in that traversal order.

## Key features

- Pure Python seating engine with no database or web-framework imports.
- MySQL constraints prevent duplicate enrollments, duplicate room coordinates, and assigning a student or seat more than once in a slot.
- Re-running allocation replaces a slot's existing rows in one transaction; exceptions roll back the changes.
- Allocation detects students enrolled in multiple exams in one slot and returns a conflict with the student IDs.
- JWT bearer authentication with `admin` and `student` roles; admin management and allocation routes require the admin role.
- Access tokens expire after 60 minutes by default (`JWT_EXPIRE_MINUTES` configures the duration).

## Quick start

Run these commands from `Backend/`. They require Python 3.11+, Docker Compose, and a local environment file with the values required by the project.
The example connection uses the MySQL `root` account as a local-development shortcut.

```bash
cp .env.example .env && docker compose up -d
python3 -m venv .venv && source .venv/bin/activate && python -m pip install -r requirements.txt uvicorn
export DATABASE_URL="mysql+pymysql://root:<URL-ENCODED-PASSWORD>@localhost:3307/examsync" JWT_SECRET="<LONG-RANDOM-SECRET>"
python -m app.scripts.seed_demo
ADMIN_EMAIL="admin@example.com" ADMIN_PASSWORD="<ADMIN-PASSWORD>" python -m app.scripts.create_admin
uvicorn app.main:app --reload
```

Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs) for Swagger. Use `POST /auth/login` with the admin email in the OAuth2 form's `username` field, then authorize Swagger with the returned bearer token.

<details>
<summary>PowerShell equivalents</summary>

Run from `Backend/`:

```powershell
Copy-Item .env.example .env; docker compose up -d
py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1; python -m pip install -r requirements.txt uvicorn
$env:DATABASE_URL = "mysql+pymysql://root:<URL-ENCODED-PASSWORD>@localhost:3307/examsync"; $env:JWT_SECRET = "<LONG-RANDOM-SECRET>"
python -m app.scripts.seed_demo
$env:ADMIN_EMAIL = "admin@example.com"; $env:ADMIN_PASSWORD = "<ADMIN-PASSWORD>"; python -m app.scripts.create_admin
uvicorn app.main:app --reload
```

</details>

## Allocation rules and design

1. Process rooms in the order supplied; the API service orders them by room ID.
2. Use columns `0, 2, 4, ...`; odd-numbered columns remain empty.
3. Fill each usable column from top to bottom before moving to the next usable column or room.
4. Choose students round-robin across sorted subject codes, skipping empty queues. The API orders each subject's queue by student roll number.
5. Return students who do not fit, ordered by subject code and then by queue order.
6. The same inputs produce the same result. Duplicate student IDs and room dimensions below one raise `ValueError`.

The trade-off is that once only one subject has students remaining, vertically neighboring assigned seats may contain that same subject. Alternate-column spacing is always enforced.

For `POST /slots/{slot_id}/allocate`, the service locks the slot row, loads the exams and enrollment roster in batched queries, checks for enrollment clashes, runs the pure engine, maps coordinates to seat IDs, then deletes and inserts allocations before one commit. A clash returns `409` without changing the saved allocation. Exceptions roll back the transaction. Missing slots or requested rooms return `404`; invalid room dimensions or engine errors return `422`.

## Data model

All tables use InnoDB and `utf8mb4`. Key uniqueness constraints are named in the models:

| Table | Purpose | Key unique constraint(s) |
|---|---|---|
| `users` | Accounts and roles | `uq_users_email` |
| `students` | Roll numbers and names; optional user link | `uq_students_roll_number`, `uq_students_user_id` |
| `subjects` | Subject codes and names | `uq_subjects_code` |
| `enrollments` | Student-to-subject links | `uq_enrollments_student_subject` |
| `rooms` | Room dimensions | `uq_rooms_name` |
| `seats` | Zero-based room coordinates | `uq_seat_room_row_col` (one seat per room coordinate) |
| `exam_slots` | Date and period label | `uq_exam_slots_date_label` |
| `exams` | Subject scheduled in a slot | `uq_exams_subject_slot` (one exam per subject per slot) |
| `allocations` | Student, seat, exam and slot assignment | `uq_alloc_slot_student` (one seat per student per slot), `uq_alloc_slot_seat` (one student per seat per slot) |

Rooms require positive dimensions; seat rows and columns must be nonnegative. A student's user link is optional. Room deletion cascades to its seats; allocation foreign keys restrict deletion.

## API overview

`/docs` contains the complete schemas and interactive API documentation.

| Method | Path | Access |
|---|---|---|
| `POST` | `/auth/register` | Public; creates a student-role account |
| `POST` | `/auth/login` | Public |
| `GET` | `/auth/me` | Authenticated |
| `POST`, `GET` | `/subjects` | Admin |
| `POST`, `GET` | `/students` | Admin |
| `POST`, `GET` | `/rooms` | Admin |
| `POST`, `GET` | `/slots` | Admin |
| `POST`, `GET` | `/exams` | Admin |
| `POST`, `GET` | `/enrollments` | Admin |
| `POST` | `/slots/{slot_id}/allocate` | Admin |
| `GET` | `/slots/{slot_id}/allocations` | Admin |

Allocation response example:

```json
{
  "assignments_by_room": [
    {
      "room_id": 1,
      "assignments": [
        {
          "student_id": 1,
          "subject_code": "DEMO-MATH",
          "room_id": 1,
          "row": 0,
          "col": 0
        }
      ]
    }
  ],
  "unseated": []
}
```

## Tests

The pure-engine tests cover ordering, room capacity, spacing, determinism, unseated students, and invalid input. FastAPI tests cover registration/login, password hashing, token errors, role checks, allocation results, clashes, and transaction rollback. These API/auth tests use an in-memory SQLite database. `tests/test_constraints.py` exercises MySQL uniqueness constraints.

Run the MySQL constraint tests against a dedicated test database, not production:

```bash
export TEST_DATABASE_URL="mysql+pymysql://<USER>:<URL-ENCODED-PASSWORD>@localhost:3307/<TEST-DATABASE>"
python -m pytest -q tests/test_constraints.py
```

The repository currently has no GitHub Actions workflow, so the badge above is a placeholder until a workflow is added. No CI coverage result is available yet.

## Future work

1. Add Alembic migrations; application startup currently uses `Base.metadata.create_all()`.
2. Add update/delete endpoints and pagination for administrative resources.
3. Add CSV import/export for students and enrollments.
4. Build a frontend for admin workflows and allocation results.
5. Consider a fallback fill pass for skipped columns, if the spacing policy permits it.

## Background

ExamSync is a standalone rebuild of the seating module from the SnapLocate–ExamSync Unified Portal capstone project at Thapar Institute.
