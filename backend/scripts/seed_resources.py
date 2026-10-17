"""Load (or remove) dummy equipment, tools and vehicles.

    python scripts/seed_resources.py            # add / refresh demo resources
    python scripts/seed_resources.py --remove   # delete only the demo resources

Records are tagged seed="demo" (resources and their maintenance logs), so
--remove never touches data you entered yourself. Nothing is assigned to a
project or worker: assign them in the app once projects exist.
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.core.config import settings  # noqa: E402

TAG = "demo"

# name, type, qty, unit, cost (Rs), bought (days ago), status, maintenance plan, description
RESOURCES = [
    ("JCB 3DX Backhoe Loader", "equipment", 1, "Nos", 3200000, 900, "available", "Every 250 engine hours", "Excavation and loading"),
    ("Tata Hitachi EX200 Excavator", "equipment", 1, "Nos", 5800000, 1300, "maintenance", "Every 500 engine hours", "Bulk excavation"),
    ("Tower Crane 6T", "equipment", 1, "Nos", 9500000, 700, "available", "Monthly inspection; load test every 6 months", "Lifting for high-rise work"),
    ("Concrete Mixer 10/7", "equipment", 3, "Nos", 85000, 500, "available", "Weekly cleaning and greasing", "Diesel drum mixer"),
    ("Concrete Vibrator (Needle)", "tool", 6, "Nos", 14000, 300, "available", "Check needle after each pour", "60mm needle vibrator"),
    ("Bar Bending Machine", "equipment", 2, "Nos", 120000, 600, "available", "Monthly", "Up to 32mm bars"),
    ("Bar Cutting Machine", "equipment", 2, "Nos", 95000, 600, "maintenance", "Monthly", "Up to 32mm bars"),
    ("Diesel Generator 62.5 kVA", "equipment", 1, "Nos", 780000, 1000, "available", "Every 250 running hours", "Site power backup"),
    ("Total Station (Survey)", "tool", 1, "Nos", 450000, 400, "available", "Calibrate every 6 months", "Setting out and levels"),
    ("Steel Scaffolding Set", "equipment", 400, "sets", 2800, 800, "available", "Inspect before every use", "Cuplock scaffolding"),
    ("Tata Ace Pickup", "vehicle", 1, "Nos", 650000, 1100, "available", "Service every 10,000 km", "Material runs between stores"),
    ("Tipper Truck 10 Wheel", "vehicle", 1, "Nos", 3400000, 1500, "retired", "Service every 10,000 km", "Retired after engine failure"),
    ("Water Pump 5 HP", "equipment", 2, "Nos", 28000, 450, "available", "Monthly", "Dewatering"),
    ("Plate Compactor", "equipment", 2, "Nos", 65000, 350, "available", "Every 100 hours", "Soil and sub-base compaction"),
    ("Welding Machine 400A", "tool", 3, "Nos", 42000, 520, "available", "Monthly cable check", "Fabrication"),
]

MAINTENANCE = {
    "Tata Hitachi EX200 Excavator": [
        (40, "routine", "500-hour service: engine oil, filters, track tension", 38000, "Hitachi service centre"),
        (2, "repair", "Hydraulic hose burst on boom; replacement parts ordered", 52000, "Hitachi service centre"),
    ],
    "Bar Cutting Machine": [(5, "repair", "Blade worn and motor overheating; sent for rewinding", 9500, "Local workshop")],
    "Tower Crane 6T": [(20, "inspection", "Monthly structural and wire-rope inspection: passed", 6000, "Third-party inspector")],
    "JCB 3DX Backhoe Loader": [(30, "routine", "250-hour service", 14500, "JCB dealer")],
    "Diesel Generator 62.5 kVA": [(15, "routine", "Oil and coolant change", 7200, "Site electrician")],
}


async def seed(db) -> None:
    now = datetime.now(timezone.utc)
    logs = 0
    for name, kind, qty, unit, cost, bought, status, plan, description in RESOURCES:
        doc = {
            "resource_name": name, "name": name, "resource_type": kind, "description": description, "quantity": qty, "unit": unit,
            "acquisition_cost": cost, "acquisition_date": now - timedelta(days=bought), "status": status,
            "assigned_to": None, "assigned_project": None, "maintenance_schedule": plan, "seed": TAG, "updated_at": now,
        }
        resource = await db.resources.find_one_and_update(
            {"resource_name": name, "seed": TAG},
            {"$set": doc, "$setOnInsert": {"created_at": now - timedelta(days=bought)}},
            upsert=True, return_document=True,
        )
        rid = str(resource["_id"])
        await db.maintenance_logs.delete_many({"resource_id": rid, "seed": TAG})
        entries = MAINTENANCE.get(name, [])
        if entries:
            await db.maintenance_logs.insert_many([
                {"resource_id": rid, "maintenance_date": now - timedelta(days=days), "maintenance_type": mtype, "description": text,
                 "cost": amount, "performed_by": by, "created_at": now - timedelta(days=days), "seed": TAG}
                for days, mtype, text, amount, by in entries
            ])
            logs += len(entries)
    print(f"Demo resources ready: {len(RESOURCES)} resources, {logs} maintenance records.")


async def remove(db) -> None:
    resources = await db.resources.delete_many({"seed": TAG})
    logs = await db.maintenance_logs.delete_many({"seed": TAG})
    print(f"Removed {resources.deleted_count} demo resources and {logs.deleted_count} demo maintenance records.")


async def main(remove_only: bool) -> None:
    db = AsyncIOMotorClient(settings.mongodb_url)[settings.mongodb_db_name]
    print(f"Database: {settings.mongodb_db_name} on {settings.mongodb_url.split('@')[-1].split('/')[0]}")
    await (remove(db) if remove_only else seed(db))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add or remove dummy resources.")
    parser.add_argument("--remove", action="store_true", help="delete only the demo resources")
    asyncio.run(main(parser.parse_args().remove))
