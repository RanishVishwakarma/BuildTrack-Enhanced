from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from motor.motor_asyncio import AsyncIOMotorDatabase


async def create_document(db: AsyncIOMotorDatabase, document_data: dict):
    document_data["created_at"] = datetime.utcnow()
    result = await db.documents.insert_one(document_data)
    return await db.documents.find_one({"_id": result.inserted_id})


async def list_documents(db: AsyncIOMotorDatabase, skip: int = 0, limit: int = 20):
    return await db.documents.find().sort("created_at", -1).skip(skip).limit(limit).to_list(limit)


async def get_document(db: AsyncIOMotorDatabase, document_id: str):
    try:
        oid = ObjectId(document_id)
    except InvalidId:
        return None

    return await db.documents.find_one({"_id": oid})


async def delete_document(db: AsyncIOMotorDatabase, document_id: str):
    try:
        oid = ObjectId(document_id)
    except InvalidId:
        return False

    result = await db.documents.delete_one({"_id": oid})
    return result.deleted_count > 0
