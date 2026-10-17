from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.main import app


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = docs or []

    def find(self, _query=None):
        return self

    def sort(self, *_args, **_kwargs):
        return self

    def skip(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    async def to_list(self, _limit=None):
        return self.docs


class FakeDb:
    def __init__(self):
        self.projects = FakeCollection([])
        self.procurements = FakeCollection([])
        self.invoices = FakeCollection([])
        self.purchase_orders = FakeCollection([])


client = TestClient(app)


async def _override_db():
    yield FakeDb()


async def _override_admin_user():
    return {"_id": "507f1f77bcf86cd799439011", "role": "admin"}


def setup_function() -> None:
    app.dependency_overrides[get_database] = _override_db
    app.dependency_overrides[get_current_user] = _override_admin_user


def teardown_function() -> None:
    app.dependency_overrides.clear()


def test_notifications_put_read_compat(monkeypatch):
    from app.modules.notifications import router as notifications_router

    async def fake_get_notification(_db, _notification_id):
        return {
            "_id": "507f1f77bcf86cd799439012",
            "receiver_id": "507f1f77bcf86cd799439011",
            "title": "hello",
            "message": "world",
            "notification_type": "info",
            "is_read": False,
            "created_at": datetime.utcnow(),
        }

    async def fake_mark_as_read(_db, _notification_id):
        return {
            "_id": "507f1f77bcf86cd799439012",
            "receiver_id": "507f1f77bcf86cd799439011",
            "title": "hello",
            "message": "world",
            "notification_type": "info",
            "is_read": True,
            "created_at": datetime.utcnow(),
            "read_at": datetime.utcnow(),
        }

    monkeypatch.setattr(notifications_router, "get_notification", fake_get_notification)
    monkeypatch.setattr(notifications_router, "mark_as_read", fake_mark_as_read)

    response = client.put("/api/v1/notifications/507f1f77bcf86cd799439012/read")

    assert response.status_code == 200
    assert response.json()["is_read"] is True


def test_reports_project_invalid_id_returns_422():
    response = client.get("/api/v1/reports/project?project_id=invalid")

    assert response.status_code == 422


def test_documents_upload_and_delete(monkeypatch):
    from app.modules.documents import router as documents_router

    upload_dir = Path("test_uploads_tmp")
    upload_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(documents_router, "UPLOAD_DIR", upload_dir)

    async def fake_create_document(_db, document_data):
        return {
            "_id": "507f1f77bcf86cd799439013",
            **document_data,
            "created_at": datetime.utcnow(),
        }

    async def fake_get_document(_db, _doc_id):
        file_path = upload_dir / "uploaded.txt"
        if not file_path.exists():
            file_path.write_text("payload", encoding="utf-8")
        return {
            "_id": "507f1f77bcf86cd799439013",
            "filename": "uploaded.txt",
            "content_type": "text/plain",
            "size_bytes": 7,
            "storage_path": str(file_path),
            "uploaded_by": "507f1f77bcf86cd799439011",
            "created_at": datetime.utcnow(),
        }

    async def fake_delete_document(_db, _doc_id):
        return True

    monkeypatch.setattr(documents_router, "create_document", fake_create_document)
    monkeypatch.setattr(documents_router, "get_document", fake_get_document)
    monkeypatch.setattr(documents_router, "delete_document", fake_delete_document)

    upload = client.post(
        "/api/v1/documents/upload",
        files={"file": ("uploaded.txt", b"payload", "text/plain")},
        data={"category": "test"},
    )
    assert upload.status_code == 200
    assert upload.json()["filename"] == "uploaded.txt"

    download = client.get("/api/v1/documents/507f1f77bcf86cd799439013/download")
    assert download.status_code == 200

    delete = client.delete("/api/v1/documents/507f1f77bcf86cd799439013")
    assert delete.status_code == 200


def test_procurements_and_vendors_top_level_aliases(monkeypatch):
    from app.modules.procurement import compat_router

    async def fake_list_vendors(_db, _skip, _limit):
        return [
            {
                "_id": "507f1f77bcf86cd799439014",
                "vendor_name": "ABC Supplies",
                "contact_person": "John",
                "email": "john@example.com",
                "phone": "1234567890",
                "rating": 4.7,
                "created_at": datetime.utcnow(),
            }
        ]

    async def fake_list_procurements(_db, _skip, _limit):
        return [
            {
                "_id": "507f1f77bcf86cd799439015",
                "vendor_id": "507f1f77bcf86cd799439014",
                "items": [
                    {
                        "item_name": "Cement",
                        "quantity": 10,
                        "unit_price": 12.0,
                        "total_cost": 120.0,
                    }
                ],
                "requested_by": "Manager",
                "request_date": datetime.utcnow(),
                "status": "pending",
                "total_amount": 120.0,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        ]

    monkeypatch.setattr(compat_router, "list_vendors", fake_list_vendors)
    monkeypatch.setattr(compat_router, "list_procurements", fake_list_procurements)

    vendors_response = client.get("/api/v1/vendors")
    procurements_response = client.get("/api/v1/procurements")

    assert vendors_response.status_code == 200
    assert vendors_response.json()[0]["vendor_name"] == "ABC Supplies"

    assert procurements_response.status_code == 200
    assert procurements_response.json()[0]["status"] == "pending"


def test_procurement_purchase_order_and_invoice_lists(monkeypatch):
    from app.modules.procurement import router as procurement_router

    # GET /purchase-orders pages through list_docs and returns {items, total}.
    async def fake_list_docs(_db, collection, *_args, **_kwargs):
        assert collection == "purchase_orders"
        return {"total": 1, "items": [
            {
                "_id": "507f1f77bcf86cd799439016",
                "procurement_id": "507f1f77bcf86cd799439015",
                "vendor_id": "507f1f77bcf86cd799439014",
                "po_number": "PO-001",
                "issue_date": datetime.utcnow(),
                "status": "issued",
                "total_amount": 120.0,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        ]}

    async def fake_list_invoices(_db, _skip, _limit):
        return [
            {
                "_id": "507f1f77bcf86cd799439017",
                "purchase_order_id": "507f1f77bcf86cd799439016",
                "invoice_number": "INV-001",
                "vendor_id": "507f1f77bcf86cd799439014",
                "invoice_date": datetime.utcnow(),
                "amount": 120.0,
                "status": "pending",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }
        ]

    monkeypatch.setattr(procurement_router, "list_docs", fake_list_docs)
    monkeypatch.setattr(procurement_router, "list_invoices", fake_list_invoices)

    purchase_orders_response = client.get("/api/v1/procurement/purchase-orders")
    invoices_response = client.get("/api/v1/procurement/invoices")

    assert purchase_orders_response.status_code == 200
    assert purchase_orders_response.json()["items"][0]["po_number"] == "PO-001"

    assert invoices_response.status_code == 200
    assert invoices_response.json()[0]["invoice_number"] == "INV-001"
