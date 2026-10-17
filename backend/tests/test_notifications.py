from datetime import datetime
from bson import ObjectId
from fastapi.testclient import TestClient
from app.main import app
from app.core.security import get_current_user
from app.db.mongodb import get_database

TEST_USER_ID = "507f1f77bcf86cd799439011"
OTHER_USER_ID = "507f1f77bcf86cd799439022"

class FakeNotificationCollection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        doc_copy = dict(doc)
        if "_id" not in doc_copy:
            doc_copy["_id"] = ObjectId()
        self.docs.append(doc_copy)
        class Result:
            inserted_id = doc_copy["_id"]
        return Result()

    async def find_one(self, query):
        for doc in self.docs:
            if "_id" in query and doc["_id"] == query["_id"]:
                return doc
        return None

    def find(self, query=None):
        self.current_query = query or {}
        return self

    def sort(self, *args, **kwargs):
        return self

    def skip(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    async def to_list(self, limit=None):
        filtered = []
        for doc in self.docs:
            match = True
            if "$or" in self.current_query:
                or_matches = False
                for cond in self.current_query["$or"]:
                    k, v = list(cond.items())[0]
                    if doc.get(k) == v:
                        or_matches = True
                        break
                if not or_matches:
                    match = False
            if "category" in self.current_query:
                if doc.get("category") != self.current_query["category"]:
                    match = False
            if "is_read" in self.current_query:
                if doc.get("is_read") != self.current_query["is_read"]:
                    match = False
            if match:
                filtered.append(doc)
        return filtered

    async def count_documents(self, query):
        self.current_query = query
        items = await self.to_list()
        return len(items)

    async def update_one(self, query, update):
        target = await self.find_one(query)
        if target and "$set" in update:
            for k, v in update["$set"].items():
                target[k] = v

    async def update_many(self, query, update):
        self.current_query = query
        items = await self.to_list()
        count = 0
        for item in items:
            if "$set" in update:
                for k, v in update["$set"].items():
                    item[k] = v
                count += 1
        return type("Result", (), {"modified_count": count})()

    async def delete_one(self, query):
        target = await self.find_one(query)
        if target:
            self.docs.remove(target)
            return type("Result", (), {"deleted_count": 1})()
        return type("Result", (), {"deleted_count": 0})()

    async def delete_many(self, query):
        return type("Result", (), {"deleted_count": 0})()


class FakeDb:
    def __init__(self):
        self.notifications = FakeNotificationCollection()
        self.projects = FakeNotificationCollection()
        self.users = FakeNotificationCollection()


fake_db = FakeDb()
client = TestClient(app)

async def _override_db():
    yield fake_db

async def _override_current_user():
    return {"_id": TEST_USER_ID, "role": "admin"}

def setup_function():
    app.dependency_overrides[get_database] = _override_db
    app.dependency_overrides[get_current_user] = _override_current_user
    fake_db.notifications.docs.clear()

def teardown_function():
    app.dependency_overrides.clear()

def test_notification_full_workflow():
    # 1. Create notification
    payload = {
        "user_id": TEST_USER_ID,
        "title": "Test Project Update",
        "message": "Project Hyderabad Metro progress updated to 80%",
        "type": "info",
        "category": "project_update",
        "entity_type": "project",
        "entity_id": "proj-123"
    }
    res = client.post("/api/v1/notifications/", json=payload)
    assert res.status_code == 200, res.text
    created = res.json()
    assert created["title"] == "Test Project Update"
    assert created["category"] == "project_update"
    assert created["is_read"] is False
    notification_id = created.get("id") or created.get("_id")
    assert notification_id is not None

    # 2. Get unread count
    res_unread = client.get("/api/v1/notifications/unread-count")
    assert res_unread.status_code == 200
    assert res_unread.json()["count"] == 1

    # 3. List notifications
    res_list = client.get("/api/v1/notifications/")
    assert res_list.status_code == 200
    items = res_list.json()
    assert len(items) == 1
    assert items[0].get("id") or items[0].get("_id") == notification_id

    # 4. Filter by category
    res_cat = client.get("/api/v1/notifications/?category=project_update")
    assert res_cat.status_code == 200
    assert len(res_cat.json()) == 1

    res_cat_empty = client.get("/api/v1/notifications/?category=procurement_alert")
    assert res_cat_empty.status_code == 200
    assert len(res_cat_empty.json()) == 0

    # 5. Mark as read
    res_read = client.patch(f"/api/v1/notifications/{notification_id}/read")
    assert res_read.status_code == 200
    assert res_read.json()["is_read"] is True

    # 6. Unread count after marking read
    res_unread_after = client.get("/api/v1/notifications/unread-count")
    assert res_unread_after.status_code == 200
    assert res_unread_after.json()["count"] == 0

    # 7. Mark all as read
    res_read_all = client.patch("/api/v1/notifications/read-all")
    assert res_read_all.status_code == 200

    # 8. Delete notification
    res_del = client.delete(f"/api/v1/notifications/{notification_id}")
    assert res_del.status_code == 200
    assert res_del.json()["message"] == "Notification deleted successfully"

    # 9. List after delete
    res_list_final = client.get("/api/v1/notifications/")
    assert res_list_final.status_code == 200
    assert len(res_list_final.json()) == 0
