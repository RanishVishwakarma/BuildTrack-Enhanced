from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


async def create_resource(db: AsyncIOMotorDatabase, resource_data: dict):
    resource_data["created_at"] = datetime.utcnow()
    resource_data["updated_at"] = datetime.utcnow()
    
    result = await db.resources.insert_one(resource_data)
    return await db.resources.find_one({"_id": result.inserted_id})


def get_resource_query(resource_id: str) -> dict:
    if ObjectId.is_valid(resource_id):
        return {"$or": [{"_id": ObjectId(resource_id)}, {"_id": resource_id}, {"id": resource_id}]}
    return {"$or": [{"_id": resource_id}, {"id": resource_id}]}


async def get_resource(db: AsyncIOMotorDatabase, resource_id: str):
    return await db.resources.find_one(get_resource_query(resource_id))


async def update_resource(db: AsyncIOMotorDatabase, resource_id: str, update_data: dict):
    update_data["updated_at"] = datetime.utcnow()
    query = get_resource_query(resource_id)
    await db.resources.update_one(
        query,
        {"$set": update_data}
    )
    return await db.resources.find_one(query)


async def delete_resource(db: AsyncIOMotorDatabase, resource_id: str):
    result = await db.resources.delete_one(get_resource_query(resource_id))
    return result.deleted_count > 0


async def list_resources(db: AsyncIOMotorDatabase, skip: int = 0, limit: int = 10):
    return await db.resources.find().skip(skip).limit(limit).to_list(limit)


async def get_resources_by_project(db: AsyncIOMotorDatabase, project_id: str):
    return await db.resources.find({"assigned_project": project_id}).to_list(None)


async def get_available_resources(db: AsyncIOMotorDatabase):
    return await db.resources.find({"status": "available"}).to_list(None)


async def assign_resource(db: AsyncIOMotorDatabase, resource_id: str, assigned_to: str, assigned_project: str):
    await db.resources.update_one(
        {"_id": ObjectId(resource_id)},
        {
            "$set": {
                "assigned_to": assigned_to,
                "assigned_project": assigned_project,
                "status": "in_use",
                "updated_at": datetime.utcnow()
            }
        }
    )
    return await db.resources.find_one({"_id": ObjectId(resource_id)})


async def unassign_resource(db: AsyncIOMotorDatabase, resource_id: str):
    await db.resources.update_one(
        {"_id": ObjectId(resource_id)},
        {
            "$set": {
                "assigned_to": None,
                "assigned_project": None,
                "status": "available",
                "updated_at": datetime.utcnow()
            }
        }
    )
    return await db.resources.find_one({"_id": ObjectId(resource_id)})


async def record_maintenance(db: AsyncIOMotorDatabase, maintenance_data: dict):
    maintenance_data["created_at"] = datetime.utcnow()
    
    result = await db.maintenance_logs.insert_one(maintenance_data)
    
    # Update resource status to maintenance
    await db.resources.update_one(
        {"_id": ObjectId(maintenance_data["resource_id"])},
        {"$set": {"status": "maintenance", "updated_at": datetime.utcnow()}}
    )
    
    return await db.maintenance_logs.find_one({"_id": result.inserted_id})


async def get_maintenance_history(db: AsyncIOMotorDatabase, resource_id: str):
    return await db.maintenance_logs.find({"resource_id": resource_id}).to_list(None)
