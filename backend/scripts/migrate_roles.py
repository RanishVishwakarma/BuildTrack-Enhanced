"""Phase 1 data migration: canonical roles and project assignments.

    python scripts/migrate_roles.py            # dry run: report only
    python scripts/migrate_roles.py --apply    # write changes

Steps
1. Rewrite legacy role values (Administrator, manager, engineer, Client, ...)
   to the seven canonical roles. Values that map to no role (e.g. "string",
   store manager, finance) are reported and left unchanged; those accounts
   cannot sign in until an admin assigns a role.
2. Seed `user_project_access` from project manager names and client emails.
   A name that matches several users is reported, not guessed.
3. Create indexes for `user_project_access` and `audit_logs`.
4. Print the admin accounts for review. Nothing is deleted.

Refuses to run against the shared `buildtrack` database unless
--allow-shared is given.
"""

import argparse
import asyncio
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.roles import ADMIN, CLIENT, PROJECT_MANAGER, legacy_duty, normalize_role  # noqa: E402

MANAGER_FIELDS = ("project_manager_id", "managerId", "manager")
CLIENT_FIELDS = ("client_email", "clientEmail", "client")


def norm(value) -> str:
    return " ".join(str(value or "").strip().lower().split())


async def run(apply: bool, allow_shared: bool) -> None:
    db_name = settings.mongodb_db_name
    if db_name == "buildtrack" and not allow_shared:
        raise SystemExit("Refusing to migrate the shared 'buildtrack' database without --allow-shared.")
    db = AsyncIOMotorClient(settings.mongodb_url)[db_name]
    mode = "APPLY" if apply else "DRY RUN"
    print(f"== Role migration ({mode}) on database '{db_name}'")

    users = await db.users.find({}, {"email": 1, "role": 1, "full_name": 1, "name": 1, "status": 1, "created_at": 1}).to_list(None)

    # 1. Roles ---------------------------------------------------------------
    changes = Counter()
    unmapped = []
    for user in users:
        stored = user.get("role")
        canonical = normalize_role(stored)
        if canonical is None:
            unmapped.append((user, legacy_duty(stored)))
            continue
        if stored != canonical:
            changes[(stored, canonical)] += 1
            if apply:
                await db.users.update_one(
                    {"_id": user["_id"]},
                    {"$set": {"role": canonical, "legacy_role": stored, "updated_at": datetime.now(timezone.utc)}},
                )
            user["role"] = canonical
    print("\n1. Role values rewritten:")
    for (old, new), count in sorted(changes.items(), key=lambda item: str(item[0])):
        print(f"   {old!r:>20} -> {new:<15} {count} user(s)")
    if not changes:
        print("   none")
    print("   Accounts with no valid role (cannot sign in until an admin assigns one):")
    for user, duty in unmapped:
        hint = f" (legacy duty '{duty}': grant its permissions after choosing a role)" if duty else ""
        print(f"   - {user.get('email')}: role={user.get('role')!r}{hint}")
    if not unmapped:
        print("   none")

    # 2. Project assignments -----------------------------------------------
    by_id = {str(u["_id"]): u for u in users}
    by_email = {norm(u.get("email")): u for u in users if u.get("email")}
    by_name = defaultdict(list)
    for u in users:
        for key in {norm(u.get("full_name")), norm(u.get("name"))} - {""}:
            by_name[key].append(u)

    grants, ambiguous, unmatched = [], [], []
    for project in await db.projects.find({}).to_list(None):
        pid, pname = str(project["_id"]), project.get("name", "(unnamed)")
        for field in MANAGER_FIELDS:
            value = project.get(field)
            if not value or norm(value) in {"unassigned", "none"}:
                continue
            candidates = []
            if str(value) in by_id:
                candidates = [by_id[str(value)]]
            elif norm(value) in by_email:
                candidates = [by_email[norm(value)]]
            else:
                candidates = by_name.get(norm(value), [])
            candidates = [c for c in candidates if c.get("role") in (PROJECT_MANAGER, ADMIN)]
            if len(candidates) == 1:
                grants.append((candidates[0], pid, pname, f"project manager ({field})"))
            elif len(candidates) > 1:
                ambiguous.append((pname, field, value, [c.get("email") for c in candidates]))
            else:
                unmatched.append((pname, field, value))
        for field in CLIENT_FIELDS:
            user = by_email.get(norm(project.get(field)))
            if user and user.get("role") == CLIENT:
                grants.append((user, pid, pname, f"client ({field})"))

    seen = set()
    print("\n2. Project assignments to create:")
    for user, pid, pname, reason in grants:
        key = (str(user["_id"]), pid)
        if key in seen:
            continue
        seen.add(key)
        print(f"   {user.get('email')} -> {pname} [{reason}]")
        if apply:
            await db.user_project_access.update_one(
                {"user_id": key[0], "project_id": pid},
                {
                    "$set": {"active": True, "updated_at": datetime.now(timezone.utc)},
                    "$setOnInsert": {"reason": f"migration: {reason}", "granted_by": None, "created_at": datetime.now(timezone.utc)},
                },
                upsert=True,
            )
    if not seen:
        print("   none")
    if ambiguous:
        print("   Ambiguous (several users share the name; assign manually):")
        for pname, field, value, emails in ambiguous:
            print(f"   - {pname}.{field}={value!r}: {', '.join(emails)}")
    if unmatched:
        print("   Not matched to any project-manager account (assign manually):")
        for pname, field, value in unmatched:
            print(f"   - {pname}.{field}={value!r}")

    # 3. Indexes ---------------------------------------------------------------
    if apply:
        await db.user_project_access.create_index([("user_id", 1), ("project_id", 1)], unique=True)
        await db.user_project_access.create_index([("project_id", 1)])
        await db.audit_logs.create_index([("timestamp", -1)])
        await db.audit_logs.create_index([("actor_id", 1), ("timestamp", -1)])
        await db.audit_logs.create_index([("event_type", 1), ("timestamp", -1)])
    print("\n3. Indexes:", "created" if apply else "would be created on user_project_access and audit_logs")

    # 4. Admin review ----------------------------------------------------------
    admins = [u for u in users if u.get("role") == ADMIN]
    print(f"\n4. Admin accounts for review ({len(admins)}). Nothing is changed here:")
    for u in sorted(admins, key=lambda item: str(item.get("created_at") or "")):
        created = u.get("created_at")
        created = created.strftime("%Y-%m-%d") if hasattr(created, "strftime") else "unknown"
        print(f"   - {u.get('email')}  created {created}  status={u.get('status')}")

    print(f"\nDone ({mode}).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate users to the seven canonical roles.")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    parser.add_argument("--allow-shared", action="store_true", help="permit running on the shared 'buildtrack' database")
    args = parser.parse_args()
    asyncio.run(run(args.apply, args.allow_shared))
