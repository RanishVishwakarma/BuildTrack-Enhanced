"""One-off: save the worker link on accounts that relied on email matching.

Worker access now follows `users.worker_id` only. Accounts created before
that were matched to a worker record by email at every login. This lists
those pairs so a manager can check them, and links them with --apply.
A pair is skipped when the email matches more than one worker or the
worker already has a login.

    .venv\\Scripts\\python.exe scripts\\link_worker_logins.py          # preview
    .venv\\Scripts\\python.exe scripts\\link_worker_logins.py --apply
"""

import asyncio
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.core.config import settings  # noqa: E402


async def main(apply: bool) -> None:
    db = AsyncIOMotorClient(settings.mongodb_url)[settings.mongodb_db_name]
    linked = {str(u["worker_id"]) async for u in db.users.find({"worker_id": {"$nin": [None, ""]}}, {"worker_id": 1})}
    query = {"role": {"$in": ["worker", "contractor"]}, "worker_id": {"$in": [None, ""]}}
    pairs, skipped = [], []
    async for user in db.users.find(query, {"email": 1, "role": 1}):
        email = str(user.get("email") or "").strip()
        workers = await db.workers.find({"email": {"$regex": f"^{re.escape(email)}$", "$options": "i"}}, {"first_name": 1, "last_name": 1}).to_list(5)
        if len(workers) != 1:
            skipped.append((email, f"{len(workers)} worker records with this email"))
        elif str(workers[0]["_id"]) in linked:
            skipped.append((email, "worker already has a login"))
        else:
            pairs.append((user, workers[0]))
            linked.add(str(workers[0]["_id"]))

    for user, worker in pairs:
        name = f"{worker.get('first_name', '')} {worker.get('last_name', '')}".strip()
        print(f"{'LINK' if apply else 'would link'}: {user['email']} ({user['role']}) -> {name} [{worker['_id']}]")
        if apply:
            await db.users.update_one({"_id": user["_id"]}, {"$set": {"worker_id": str(worker["_id"]), "updated_at": datetime.now(timezone.utc)}})
    for email, reason in skipped:
        print(f"skipped: {email} ({reason})")
    if not pairs and not skipped:
        print("Nothing to link.")
    elif not apply and pairs:
        print("Check the list above, then re-run with --apply.")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
