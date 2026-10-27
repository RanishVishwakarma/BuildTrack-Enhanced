"""One-off: turn email-matched client access into explicit grants.

Clients used to see any project whose client email matched their login
email, checked at every request. Access now comes only from
`user_project_access`. This lists the client accounts that relied on the
email match so you can check them, and grants that access with --apply.
Remove any account you do not recognise instead of applying.

    .venv\\Scripts\\python.exe scripts\\grant_client_access.py          # preview
    .venv\\Scripts\\python.exe scripts\\grant_client_access.py --apply
"""

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.core.access import grant_project_access  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.modules.projects.router import CLIENT_ACCESS_REASON  # noqa: E402

EMAIL_FIELDS = ("client_email", "clientEmail", "client")


async def main(apply: bool) -> None:
    db = AsyncIOMotorClient(settings.mongodb_url)[settings.mongodb_db_name]
    pending = []
    async for user in db.users.find({"role": "client"}, {"email": 1, "full_name": 1, "name": 1}):
        email = str(user.get("email") or "").strip()
        if not email:
            continue
        match = {"$regex": f"^{re.escape(email)}$", "$options": "i"}
        async for project in db.projects.find({"$or": [{f: match} for f in EMAIL_FIELDS]}, {"name": 1}):
            granted = await db.user_project_access.find_one({"user_id": str(user["_id"]), "project_id": str(project["_id"]), "active": True})
            if not granted:
                pending.append((user, project))

    for user, project in pending:
        print(f"{'GRANT' if apply else 'would grant'}: {user['email']} -> {project.get('name')}")
        if apply:
            await grant_project_access(db, user_id=str(user["_id"]), project_id=str(project["_id"]), granted_by=None, reason=CLIENT_ACCESS_REASON)
    if not pending:
        print("Nothing to grant: every client already has explicit access.")
    elif not apply:
        print("Check the list above, then re-run with --apply.")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
