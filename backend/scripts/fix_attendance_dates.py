"""One-off: repair attendance saved before dates were calendar days.

Older records stored the day as a UTC instant (an 18 Oct mark in India was
saved as 17 Oct 18:30), so the roster showed the day as unmarked and each
click added another record. This moves every record to its site calendar
day (APP_TIMEZONE) and, where a worker then has several records for one
day, keeps the most recently updated one and removes the rest.

    .venv\\Scripts\\python.exe scripts\\fix_attendance_dates.py          # preview
    .venv\\Scripts\\python.exe scripts\\fix_attendance_dates.py --apply
"""

import asyncio
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.modules.workforce.attendance_dates import work_day  # noqa: E402


async def main(apply: bool) -> None:
    db = AsyncIOMotorClient(settings.mongodb_url)[settings.mongodb_db_name]
    records = await db.attendance.find({}).to_list(None)
    moved, groups = [], defaultdict(list)
    for record in records:
        day = work_day(record.get("date")) if record.get("date") else None
        if day is None:
            continue
        if day != record["date"]:
            moved.append((record, day))
        groups[(str(record.get("worker_id")), day)].append(record)

    extra = []
    for (worker_id, day), items in groups.items():
        if len(items) > 1:
            items.sort(key=lambda r: r.get("updated_at") or r.get("created_at"), reverse=True)
            keep, drop = items[0], items[1:]
            extra.extend(drop)
            print(f"worker {worker_id} on {day:%d %b %Y}: {len(items)} records, keeping the latest ({keep.get('status')}), removing {len(drop)}")

    print(f"{len(moved)} of {len(records)} records move to their site day ({settings.app_timezone}); {len(extra)} duplicates.")
    if not apply:
        if moved or extra:
            print("Preview only. Re-run with --apply to make these changes.")
        return
    dropped = {r["_id"] for r in extra}
    for record, day in moved:
        if record["_id"] not in dropped:
            await db.attendance.update_one({"_id": record["_id"]}, {"$set": {"date": day}})
    if dropped:
        await db.attendance.delete_many({"_id": {"$in": list(dropped)}})
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
