from datetime import datetime

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase


async def create_report(db: AsyncIOMotorDatabase, report_data: dict):
    report_data["created_at"] = datetime.utcnow()
    report_data["updated_at"] = datetime.utcnow()
    report_data["status"] = "completed"
    
    result = await db.reports.insert_one(report_data)
    return await db.reports.find_one({"_id": result.inserted_id})


async def get_report(db: AsyncIOMotorDatabase, report_id: str):
    return await db.reports.find_one({"_id": ObjectId(report_id)})


async def list_reports(db: AsyncIOMotorDatabase, skip: int = 0, limit: int = 10):
    return await db.reports.find().sort("created_at", -1).skip(skip).limit(limit).to_list(limit)


async def get_reports_by_type(db: AsyncIOMotorDatabase, report_type: str):
    return await db.reports.find({"report_type": report_type}).sort("created_at", -1).to_list(None)


async def get_reports_by_project(db: AsyncIOMotorDatabase, project_id: str):
    return await db.reports.find({"project_id": project_id}).sort("created_at", -1).to_list(None)


async def delete_report(db: AsyncIOMotorDatabase, report_id: str):
    result = await db.reports.delete_one({"_id": ObjectId(report_id)})
    return result.deleted_count > 0


async def get_dashboard_metrics(db: AsyncIOMotorDatabase):
    """Calculate key metrics for dashboard"""
    metrics = {}
    
    # Project metrics
    total_projects = await db.projects.count_documents({})
    active_projects = await db.projects.count_documents({"status": {"$in": ["active", "in_progress"]}})
    
    # Resource metrics
    total_resources = await db.resources.count_documents({})
    available_resources = await db.resources.count_documents({"status": "available"})
    
    # Worker metrics
    total_workers = await db.workers.count_documents({})
    
    # Inventory metrics
    inventory_items = await db.inventory.find().to_list(None)
    total_inventory_value = sum(item.get("quantity", 0) * item.get("unit_cost", 0) for item in inventory_items)
    low_stock_items = await db.inventory.count_documents({
        "$expr": {"$lte": ["$quantity", "$reorder_level"]}
    })
    
    # Procurement metrics
    pending_procurements = await db.procurements.count_documents({"status": "pending"})
    
    # Calculate total expenses (from procurements and maintenance)
    procurements = await db.procurements.find().to_list(None)
    total_expenses = sum(p.get("total_amount", 0) for p in procurements)
    
    maintenance_logs = await db.maintenance_logs.find().to_list(None)
    total_expenses += sum(m.get("cost", 0) for m in maintenance_logs)
    
    metrics = {
        "total_projects": total_projects,
        "active_projects": active_projects,
        "total_resources": total_resources,
        "available_resources": available_resources,
        "total_workers": total_workers,
        "total_inventory_value": total_inventory_value,
        "low_stock_items": low_stock_items,
        "pending_procurements": pending_procurements,
        "total_expenses": total_expenses,
    }
    
    return metrics


async def get_project_report_summary(db: AsyncIOMotorDatabase, project_id: str | None = None):
    project_filter = {"_id": ObjectId(project_id)} if project_id else {}
    projects = await db.projects.find(project_filter).to_list(None)

    output = []
    for project in projects:
        pid = str(project.get("_id"))
        procurements = await db.procurements.find({"project_id": pid}).to_list(None)
        total_procurement_cost = sum(item.get("total_amount", 0) for item in procurements)
        output.append(
            {
                "project_id": pid,
                "project_name": project.get("name") or project.get("project_name") or "Unnamed Project",
                "status": project.get("status", "unknown"),
                "procurements_count": len(procurements),
                "total_procurement_cost": total_procurement_cost,
            }
        )

    return output


async def get_procurement_report_summary(db: AsyncIOMotorDatabase):
    procurements = await db.procurements.find().to_list(None)
    invoices = await db.invoices.find().to_list(None)

    by_status: dict[str, int] = {}
    for procurement in procurements:
        key = procurement.get("status", "unknown")
        by_status[key] = by_status.get(key, 0) + 1

    total_value = sum(item.get("total_amount", 0) for item in procurements)
    invoice_total = sum(item.get("amount", 0) for item in invoices)

    return {
        "total_procurements": len(procurements),
        "procurement_value": total_value,
        "status_breakdown": by_status,
        "total_invoices": len(invoices),
        "invoice_amount_total": invoice_total,
    }
