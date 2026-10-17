from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


async def create_notification(db: AsyncIOMotorDatabase, notification_data: dict):
    now = datetime.now(timezone.utc)
    notification_data.setdefault("created_at", now)
    notification_data.setdefault("updated_at", now)
    notification_data.setdefault("is_read", False)

    target_user = notification_data.get("user_id") or notification_data.get("receiver_id")
    if target_user:
        notification_data["user_id"] = str(target_user)
        notification_data["receiver_id"] = str(target_user)

    category = notification_data.get("category") or "system"
    notification_data["category"] = category
    notification_data.setdefault("type", notification_data.get("notification_type", "info"))

    result = await db.notifications.insert_one(notification_data)
    return await db.notifications.find_one({"_id": result.inserted_id})


async def create_notifications_for_users(db: AsyncIOMotorDatabase, user_ids: list[str], notification_data: dict):
    created_docs = []
    for uid in set(user_ids):
        if not uid:
            continue
        data_copy = dict(notification_data)
        data_copy["user_id"] = str(uid)
        doc = await create_notification(db, data_copy)
        created_docs.append(doc)
    return created_docs


async def get_notification(db: AsyncIOMotorDatabase, notification_id: str):
    if not ObjectId.is_valid(notification_id):
        return None
    return await db.notifications.find_one({"_id": ObjectId(notification_id)})


async def get_user_notifications(
    db: AsyncIOMotorDatabase,
    user_id: str,
    skip: int = 0,
    limit: int = 20,
    category: Optional[str] = None,
    is_read: Optional[bool] = None,
):
    query = {"$or": [{"user_id": user_id}, {"receiver_id": user_id}]}
    if category and category.lower() != "all":
        query["category"] = category
    if is_read is not None:
        query["is_read"] = is_read

    cursor = db.notifications.find(query).sort("created_at", -1).skip(skip).limit(limit)
    return await cursor.to_list(limit)


async def get_unread_notifications(db: AsyncIOMotorDatabase, user_id: str):
    query = {
        "$or": [{"user_id": user_id}, {"receiver_id": user_id}],
        "is_read": False,
    }
    return await db.notifications.find(query).sort("created_at", -1).to_list(100)


async def get_unread_notification_count(db: AsyncIOMotorDatabase, user_id: str, category: Optional[str] = None):
    query = {
        "$or": [{"user_id": user_id}, {"receiver_id": user_id}],
        "is_read": False,
    }
    if category and category.lower() != "all":
        query["category"] = category
    return await db.notifications.count_documents(query)


async def mark_as_read(db: AsyncIOMotorDatabase, notification_id: str, user_id: Optional[str] = None):
    if not ObjectId.is_valid(notification_id):
        return None

    query = {"_id": ObjectId(notification_id)}
    if user_id:
        query["$or"] = [{"user_id": user_id}, {"receiver_id": user_id}]

    now = datetime.utcnow()
    await db.notifications.update_one(
        query,
        {
            "$set": {
                "is_read": True,
                "read_at": now,
                "updated_at": now,
            }
        },
    )
    return await db.notifications.find_one({"_id": ObjectId(notification_id)})


async def mark_all_as_read(db: AsyncIOMotorDatabase, user_id: str):
    now = datetime.utcnow()
    result = await db.notifications.update_many(
        {
            "$or": [{"user_id": user_id}, {"receiver_id": user_id}],
            "is_read": False,
        },
        {
            "$set": {
                "is_read": True,
                "read_at": now,
                "updated_at": now,
            }
        },
    )
    return result.modified_count


async def delete_notification(db: AsyncIOMotorDatabase, notification_id: str, user_id: Optional[str] = None):
    if not ObjectId.is_valid(notification_id):
        return False

    query = {"_id": ObjectId(notification_id)}
    if user_id:
        query["$or"] = [{"user_id": user_id}, {"receiver_id": user_id}]

    result = await db.notifications.delete_one(query)
    return result.deleted_count > 0


async def delete_old_notifications(db: AsyncIOMotorDatabase, days: int = 30):
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    result = await db.notifications.delete_many({"created_at": {"$lt": cutoff_date}})
    return result.deleted_count


async def check_and_create_deadline_notifications(db: AsyncIOMotorDatabase):
    """
    Scans projects, tasks, and procurement items for approaching deadlines
    and generates deadline notifications for relevant users.
    """
    count = 0
    now = datetime.utcnow()
    three_days_later = now + timedelta(days=3)

    # 1. Check Projects near end_date
    projects = await db.projects.find().to_list(100)
    users = await db.users.find().to_list(100)
    all_user_ids = [str(u["_id"]) for u in users]

    for p in projects:
        end_date = p.get("end_date") or p.get("endDate")
        if isinstance(end_date, str):
            try:
                end_date = datetime.fromisoformat(end_date)
            except ValueError:
                continue

        if end_date and now <= end_date <= three_days_later:
            p_id = str(p["_id"])
            p_name = p.get("name") or p.get("title") or "Project"
            manager_id = p.get("project_manager_id") or p.get("managerId")

            target_users = [manager_id] if manager_id else all_user_ids
            for uid in target_users:
                if not uid:
                    continue
                # Avoid duplicate within 24 hours
                recent = await db.notifications.find_one({
                    "user_id": str(uid),
                    "category": "deadline",
                    "entity_id": p_id,
                    "created_at": {"$gt": now - timedelta(hours=24)}
                })
                if not recent:
                    await create_notification(db, {
                        "user_id": str(uid),
                        "title": "Project Deadline Approaching",
                        "message": f"Project '{p_name}' deadline is on {end_date.strftime('%Y-%m-%d')}.",
                        "type": "warning",
                        "category": "deadline",
                        "entity_type": "project",
                        "entity_id": p_id,
                    })
                    count += 1

    return count

