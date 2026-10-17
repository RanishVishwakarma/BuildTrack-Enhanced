"""First-time setup for a new, empty BuildTrack database.

    python scripts/setup_database.py --admin-email you@example.com

Creates the indexes and the first administrator account. The password is
typed at the prompt (not shown, not stored in shell history). Safe to re-run:
indexes are idempotent and an existing account is never overwritten.
"""

import argparse
import asyncio
import getpass
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from pydantic import EmailStr, TypeAdapter, ValidationError  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.indexes import ensure_indexes  # noqa: E402


def ask_password() -> str:
    while True:
        first = getpass.getpass("Admin password (min 8 characters): ")
        if len(first) < 8:
            print("Too short, try again.")
            continue
        if getpass.getpass("Repeat password: ") != first:
            print("Passwords do not match, try again.")
            continue
        return first


async def main(email: str, name: str) -> None:
    host = settings.mongodb_url.split("@")[-1].split("/")[0]
    db = AsyncIOMotorClient(settings.mongodb_url)[settings.mongodb_db_name]
    await db.command("ping")
    print(f"Connected to {host}, database '{settings.mongodb_db_name}'.")

    await ensure_indexes(db)
    await db.users.create_index("email", unique=True)
    print("Indexes ready.")

    if await db.users.find_one({"email": {"$regex": f"^{email}$", "$options": "i"}}):
        print(f"An account for {email} already exists; it was left unchanged.")
        return
    password = ask_password()
    now = datetime.now(timezone.utc)
    await db.users.insert_one({
        "email": email.lower(), "full_name": name, "name": name, "role": "admin", "status": "active",
        "password_hash": hash_password(password), "created_at": now, "updated_at": now,
    })
    print(f"Administrator {email} created. Sign in with it in the app.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Set up a new BuildTrack database.")
    parser.add_argument("--admin-email", required=True)
    parser.add_argument("--admin-name", default="Administrator")
    args = parser.parse_args()
    try:
        email = str(TypeAdapter(EmailStr).validate_python(args.admin_email))
    except ValidationError:
        raise SystemExit("That is not a valid email address.")
    asyncio.run(main(email, args.admin_name))
