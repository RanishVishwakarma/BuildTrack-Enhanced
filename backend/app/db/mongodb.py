from collections.abc import AsyncGenerator

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.core.config import settings

# High-performance connection pool with pre-warmed connections
mongo_client = AsyncIOMotorClient(
    settings.mongodb_url,
    serverSelectionTimeoutMS=15000,
    connectTimeoutMS=15000,
    socketTimeoutMS=20000,
    maxPoolSize=50,
    minPoolSize=5,
    maxIdleTimeMS=45000,
    retryWrites=True,
)

database = mongo_client[settings.mongodb_db_name]


async def get_database() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    yield database


async def ping_database() -> bool:
    await database.command("ping")
    return True
