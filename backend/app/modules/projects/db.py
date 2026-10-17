from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


async def create_project(db: AsyncIOMotorDatabase, project_data: dict):
    project_data["created_at"] = datetime.utcnow()
    project_data["updated_at"] = datetime.utcnow()
    project_data["milestones"] = []
    
    result = await db.projects.insert_one(project_data)
    return await db.projects.find_one({"_id": result.inserted_id})


async def get_project(db: AsyncIOMotorDatabase, project_id: str):
    return await db.projects.find_one({"_id": ObjectId(project_id)})


async def update_project(db: AsyncIOMotorDatabase, project_id: str, update_data: dict):
    update_data["updated_at"] = datetime.utcnow()
    await db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {"$set": update_data}
    )
    return await db.projects.find_one({"_id": ObjectId(project_id)})


async def delete_project(db: AsyncIOMotorDatabase, project_id: str):
    result = await db.projects.delete_one({"_id": ObjectId(project_id)})
    return result.deleted_count > 0


async def list_projects(db: AsyncIOMotorDatabase, skip: int = 0, limit: int = 100):
    return await db.projects.find().skip(skip).limit(limit).to_list(limit)


async def get_projects_by_manager(db: AsyncIOMotorDatabase, manager_id: str):
    return await db.projects.find({"project_manager_id": manager_id}).to_list(None)


async def add_milestone(db: AsyncIOMotorDatabase, project_id: str, milestone: dict):
    milestone["_id"] = ObjectId()
    milestone["created_at"] = datetime.utcnow()
    milestone["updated_at"] = datetime.utcnow()
    
    await db.projects.update_one(
        {"_id": ObjectId(project_id)},
        {"$push": {"milestones": milestone}}
    )
    return milestone
