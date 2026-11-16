import os

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole


def main() -> None:
    email = os.getenv("ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD")
    if not email or not password:
        raise RuntimeError("Set ADMIN_EMAIL and ADMIN_PASSWORD before creating an admin.")

    with SessionLocal() as session:
        existing_user = session.scalar(select(User).where(User.email == email))
        if existing_user is not None:
            print("An account with that email already exists.")
            return

        session.add(
            User(
                email=email,
                password_hash=hash_password(password),
                role=UserRole.ADMIN,
            )
        )
        session.commit()
        print("Admin account created.")


if __name__ == "__main__":
    main()
