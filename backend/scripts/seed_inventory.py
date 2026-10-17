"""Load (or remove) dummy inventory for trying the app.

    python scripts/seed_inventory.py            # add / refresh demo items
    python scripts/seed_inventory.py --remove   # delete only the demo items

Every record written is tagged seed="demo", so --remove never touches data
you entered yourself. Re-running updates the demo items instead of
duplicating them.
"""

import argparse
import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.core.config import settings  # noqa: E402

TAG = "demo"

# material, unit, quantity, unit cost (Rs), reorder level, location, typical daily use
ITEMS = [
    ("Cement OPC 53 Grade", "bags", 420, 380, 100, "Main Yard", 18),
    ("Cement OPC 53 Grade", "bags", 40, 380, 30, "Site Store B", 4),
    ("Cement PPC", "bags", 60, 360, 80, "Main Yard", 6),
    ("TMT Steel Bar 12mm", "kg", 5200, 68, 2000, "Main Yard", 150),
    ("TMT Steel Bar 16mm", "kg", 1400, 67, 1500, "Main Yard", 90),
    ("River Sand", "m3", 45, 3200, 20, "Main Yard", 2),
    ("M-Sand", "m3", 0, 2600, 15, "Main Yard", 0),
    ("Coarse Aggregate 20mm", "m3", 60, 1800, 25, "Main Yard", 3),
    ("Red Bricks", "pieces", 18000, 9, 5000, "Site Store A", 600),
    ("AAC Blocks 600x200x150", "pieces", 900, 55, 1000, "Site Store A", 40),
    ("Binding Wire", "kg", 140, 85, 50, "Site Store A", 4),
    ("Plywood Shuttering 12mm", "sheets", 210, 1450, 80, "Main Yard", 3),
    ("PVC Pipe 4 inch", "pieces", 75, 620, 30, "Site Store B", 2),
    ("Electrical Wire 2.5 sq mm", "rolls", 32, 2150, 10, "Site Store B", 1),
    ("Exterior Emulsion Paint", "litres", 180, 320, 60, "Site Store B", 5),
    ("Waterproofing Compound", "litres", 25, 210, 40, "Site Store A", 2),
    ("Safety Helmets", "pieces", 48, 250, 30, "Site Store A", 0),
]


def status_for(quantity: float, reorder: float) -> str:
    if quantity <= 0:
        return "out_of_stock"
    if quantity <= reorder:
        return "low_stock"
    return "in_stock"


async def seed(db) -> None:
    now = datetime.now(timezone.utc)
    rng = random.Random(42)  # same demo data every run
    items_written = movements = 0
    for name, unit, qty, cost, reorder, location, daily in ITEMS:
        doc = {
            "material_name": name, "material": name, "itemName": name, "unit": unit,
            "quantity": qty, "stock_quantity": qty, "unit_cost": cost, "reorder_level": reorder,
            "location": location, "status": status_for(qty, reorder), "supplier_id": None,
            "seed": TAG, "updated_at": now,
        }
        result = await db.inventory.find_one_and_update(
            {"material_name": name, "location": location, "seed": TAG},
            {"$set": doc, "$setOnInsert": {"created_at": now - timedelta(days=45)}},
            upsert=True, return_document=True,
        )
        items_written += 1
        item_id = str(result["_id"])

        # 30 days of history: one delivery in, near-daily issues out.
        await db.inventory_transactions.delete_many({"item_id": item_id, "seed": TAG})
        history = []
        if daily:
            history.append({"transaction_type": "in", "quantity": int(daily * 25), "reason": "Delivery received", "created_at": now - timedelta(days=28)})
            for day in range(27, 0, -1):
                if rng.random() < 0.8:
                    used = max(1, int(daily * rng.uniform(0.6, 1.4)))
                    history.append({"transaction_type": "out", "quantity": used, "reason": "Issued to site", "created_at": now - timedelta(days=day, hours=rng.randint(0, 8))})
        if name == "Cement OPC 53 Grade" and location == "Main Yard":
            history.append({"transaction_type": "out", "quantity": 25, "reason": "Damaged bags written off (wastage)", "created_at": now - timedelta(days=3)})
        if history:
            await db.inventory_transactions.insert_many([
                {**h, "item_id": item_id, "created_by": "Demo data", "seed": TAG} for h in history
            ])
            movements += len(history)
    print(f"Demo inventory ready: {items_written} items, {movements} stock movements.")


async def remove(db) -> None:
    items = await db.inventory.delete_many({"seed": TAG})
    moves = await db.inventory_transactions.delete_many({"seed": TAG})
    print(f"Removed {items.deleted_count} demo items and {moves.deleted_count} demo stock movements.")


async def main(remove_only: bool) -> None:
    db = AsyncIOMotorClient(settings.mongodb_url)[settings.mongodb_db_name]
    host = settings.mongodb_url.split("@")[-1].split("/")[0]
    print(f"Database: {settings.mongodb_db_name} on {host}")
    await (remove(db) if remove_only else seed(db))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add or remove dummy inventory.")
    parser.add_argument("--remove", action="store_true", help="delete only the demo items")
    asyncio.run(main(parser.parse_args().remove))
