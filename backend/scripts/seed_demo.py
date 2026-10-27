"""Load (or remove) a small, connected demo dataset across the whole app.

    python scripts/seed_demo.py            # add demo data (re-running replaces it)
    python scripts/seed_demo.py --remove   # delete only this demo data

Three projects with milestones, tasks, workers, allocations, two weeks of
attendance, shifts, vendors, material requests, purchase orders (GST),
deliveries, invoices (one deliberately mismatched for the 3-way match),
a payment, safety reports with a corrective action, improvement
suggestions and saved reports. Tower B is assigned to the first existing
project manager (and its site engineers, contractors and clients); Metro
Plaza and the Hospital Annex stay unassigned until an admin assigns them.

Every record is tagged seed="demo-site", so --remove never touches data you
entered yourself (or the inventory/resources demo, which has its own script).
Emails use the reserved example.com domain, so no real address is ever used.
"""

import argparse
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bson import ObjectId  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.modules.procurement.gst import price_order  # noqa: E402

TAG = "demo-site"
COLLECTIONS = [
    "projects", "project_milestones", "user_project_access", "workers", "workforce_allocations", "attendance", "shifts",
    "shift_assignments", "tasks", "vendors", "material_requests", "purchase_orders", "deliveries", "invoices", "payments",
    "safety_reports", "corrective_actions", "suggestions", "generated_reports",
]

UTC_NOW = datetime.now(timezone.utc).replace(tzinfo=None)  # Mongo stores naive UTC
SITE = ZoneInfo(settings.app_timezone)
TODAY = datetime.now(SITE).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)  # site calendar day


def ago(days: float, hours: float = 0) -> datetime:
    return UTC_NOW - timedelta(days=days, hours=hours)


def ahead(days: float) -> datetime:
    return UTC_NOW + timedelta(days=days)


def site_time(day: datetime, hhmm: str) -> datetime:
    """A local clock time on a site day, as naive UTC."""
    h, m = map(int, hhmm.split(":"))
    return day.replace(hour=h, minute=m, tzinfo=SITE).astimezone(timezone.utc).replace(tzinfo=None)


def tagged(doc: dict) -> dict:
    return {"seed": TAG, "created_at": doc.pop("created_at", ago(30)), "updated_at": doc.pop("updated_at", ago(1)), **doc}


async def next_code(db, name: str, prefix: str) -> str:
    counter = await db.counters.find_one_and_update({"_id": name}, {"$inc": {"seq": 1}}, upsert=True, return_document=True)
    return f"{prefix}-{counter['seq']:05d}"


async def users_by_role(db) -> dict[str, list[dict]]:
    aliases = {"projectmanager": "project_manager", "siteengineer": "site_engineer", "administrator": "admin"}
    found: dict[str, list[dict]] = {}
    async for user in db.users.find({}, {"role": 1, "full_name": 1, "email": 1}):
        role = aliases.get(str(user.get("role")).lower().replace(" ", ""), str(user.get("role")).lower())
        found.setdefault(role, []).append(user)
    return found


async def remove(db) -> dict:
    return {name: (await db[name].delete_many({"seed": TAG})).deleted_count for name in COLLECTIONS}


async def seed(db) -> dict:
    await remove(db)
    people = await users_by_role(db)
    admin = (people.get("admin") or [{}])[0]
    pm = (people.get("project_manager") or [admin])[0]
    engineer = (people.get("site_engineer") or [pm])[0]
    actor = str(pm.get("_id", ""))

    # ------------------------------------------------------------ projects
    projects = {
        "tower": {"name": "Green Valley Residency - Tower B", "category": "Residential", "location": "Yelahanka, Bengaluru", "status": "active",
                  "start": ago(95), "end": ahead(185), "budget": 45000000.0, "progress": 38.0,
                  "description": "G+12 residential tower with 96 apartments, basement parking and rooftop amenities. Currently on floor 5 slab work."},
        "plaza": {"name": "Metro Commercial Plaza", "category": "Commercial", "location": "Whitefield, Bengaluru", "status": "active",
                  "start": ago(42), "end": ahead(320), "budget": 98000000.0, "progress": 12.0,
                  "description": "Four-storey retail and office complex near the metro station. Foundation and basement retaining walls in progress."},
        "annex": {"name": "City Hospital Annex", "category": "Institutional", "location": "Hebbal, Bengaluru", "status": "planning",
                  "start": ahead(20), "end": ahead(420), "budget": 62000000.0, "progress": 0.0,
                  "description": "Three-storey hospital annex with an OT block. Drawings approved; site mobilisation planned."},
    }
    client = (people.get("client") or [{}])[0]
    pid = {}
    for key, p in projects.items():
        doc = tagged({"name": p["name"], "description": p["description"], "category": p["category"], "location": p["location"],
                      "client": "Demo Client Pvt Ltd", "client_email": client.get("email", "client@example.com") if key == "tower" else "client@example.com",
                      "project_manager_id": actor if key == "tower" and people.get("project_manager") else "unassigned", "start_date": p["start"], "end_date": p["end"], "budget": p["budget"],
                      "progress": p["progress"], "status": p["status"], "milestones": [], "created_at": p["start"] - timedelta(days=10)})
        doc["clientEmail"] = doc["client_email"]
        pid[key] = str((await db.projects.insert_one(doc)).inserted_id)

    # Only Tower B is handed out: the first project manager manages it and the
    # site team works on it. Metro Plaza and the Hospital Annex stay unassigned
    # until an admin gives them to a manager, so each manager sees only their own.
    team = [(people.get("project_manager") or [])[:1], people.get("site_engineer", []), people.get("contractor", []), people.get("client", [])]
    for reason, users in zip(("project manager", "Demo data", "Demo data", "project client"), team):
        for user in users:
            await db.user_project_access.insert_one(tagged({"project_id": pid["tower"], "user_id": str(user["_id"]), "active": True,
                                                             "granted_by": str(admin.get("_id", "")), "reason": reason}))

    milestones = [
        ("tower", "Foundation and basement", -60, "Completed", 100), ("tower", "Superstructure up to floor 6", 25, "In Progress", 65),
        ("tower", "Brickwork and plastering", 110, "Not Started", 0), ("plaza", "Excavation and shoring", -10, "Completed", 100),
        ("plaza", "Basement raft and retaining walls", 45, "In Progress", 30), ("annex", "Site mobilisation", 25, "Not Started", 0),
    ]
    for key, title, due, status, progress in milestones:
        due_date = (TODAY + timedelta(days=due)).date().isoformat()
        await db.project_milestones.insert_one(tagged({"projectId": pid[key], "project_id": pid[key], "title": title, "dueDate": due_date,
                                                       "due_date": due_date, "status": status, "progress": progress, "created_by": actor}))

    # ------------------------------------------------------------ workforce
    workers = [
        ("Ramesh", "Gowda", "SUPERVISOR", "Site supervisor", "Site Supervisor", 14, 1400, "tower"),
        ("Suresh", "Kumar", "SKILLED_WORKER", "Mason", "Senior Mason", 9, 950, "tower"),
        ("Manjunath", "N", "SKILLED_WORKER", "Bar bender", "Bar Bender", 7, 900, "tower"),
        ("Imran", "Pasha", "SKILLED_WORKER", "Carpenter", "Shuttering Carpenter", 11, 950, "tower"),
        ("Lakshmi", "Devi", "UNSKILLED_WORKER", "Helper", "Helper", 3, 600, "tower"),
        ("Vijay", "Raj", "SKILLED_WORKER", "Electrician", "Electrician", 6, 1000, "plaza"),
        ("Anil", "Shetty", "SKILLED_WORKER", "Crane operator", "Crane Operator", 12, 1300, "plaza"),
        ("Prakash", "Rao", "SKILLED_WORKER", "Welder", "Welder", 8, 950, "plaza"),
        ("Kavya", "S", "ENGINEER", "Civil engineer", "Junior Engineer", 2, 1600, "plaza"),
        ("Mohan", "Das", "UNSKILLED_WORKER", "Helper", "Helper", 1, 600, "plaza"),
    ]
    wid, worker_project = {}, {}
    for i, (first, last, category, skill, designation, years, day_rate, key) in enumerate(workers, start=1):
        doc = tagged({"worker_code": f"WRK-D{i:02d}", "first_name": first, "last_name": last, "email": f"{first.lower()}.{last.lower()}@example.com",
                      "phone": f"98450{i:05d}", "category": category, "skill_type": skill, "designation": designation, "experience_years": float(years),
                      "employment_type": "CONTRACT" if category == "UNSKILLED_WORKER" else "FULL_TIME", "joining_date": ago(30 * years + 40),
                      "salary_type": "DAILY", "hourly_rate": round(day_rate / 8, 2), "salary_amount": float(day_rate), "project_id": pid[key], "status": "assigned"})
        wid[first] = str((await db.workers.insert_one(doc)).inserted_id)
        worker_project[first] = pid[key]
        await db.workforce_allocations.insert_one(tagged({"worker_id": wid[first], "project_id": pid[key], "role": designation,
                                                          "start_date": ago(40), "end_date": None, "status": "ACTIVE"}))

    attendance = 0
    for back in range(1, 15):
        day = TODAY - timedelta(days=back)
        if day.weekday() == 6:  # Sunday off
            continue
        for n, (first, *_rest) in enumerate(workers):
            # Mohan is often absent (shows in Low attendance); others mostly present.
            status = "absent" if (first == "Mohan" and back % 3 != 0) else "leave" if (back + n) % 13 == 0 else "absent" if (back + n) % 17 == 0 else "present"
            record = {"worker_id": wid[first], "project_id": worker_project[first], "date": day, "status": status,
                      "check_in_time": None, "check_out_time": None, "hours_worked": None, "overtime_hours": 0, "remarks": None}
            if status == "present":
                overtime = 2 if (back + n) % 5 == 0 else 0
                record.update(check_in_time=site_time(day, "09:00"), check_out_time=site_time(day, f"{18 + overtime}:00"),
                              hours_worked=8.0 + overtime, overtime_hours=overtime)
            elif status == "leave":
                record["remarks"] = "Approved leave"
            await db.attendance.insert_one(tagged({**record, "created_at": site_time(day, "19:00"), "updated_at": site_time(day, "19:00")}))
            attendance += 1

    shifts = {"day": ("Day shift", "08:00", "17:00", "tower"), "pour": ("Night concrete pour", "20:00", "04:00", "tower"), "general": ("General shift", "09:00", "18:00", "plaza")}
    sid = {}
    for key, (name, start, end, project) in shifts.items():
        sid[key] = str((await db.shifts.insert_one(tagged({"name": name, "project_id": pid[project], "start_time": start, "end_time": end,
                                                            "description": "Demo shift", "status": "ACTIVE"}))).inserted_id)
    for ahead_days in range(0, 7):
        day = TODAY + timedelta(days=ahead_days)
        if day.weekday() == 6:
            continue
        for first, *_rest in workers:
            tower = worker_project[first] == pid["tower"]
            shift = "pour" if tower and first in {"Suresh", "Manjunath"} and ahead_days == 2 else "day" if tower else "general"
            await db.shift_assignments.insert_one(tagged({"worker_id": wid[first], "shift_id": sid[shift], "project_id": worker_project[first],
                                                          "date": day, "status": "ACTIVE"}))

    # ------------------------------------------------------------ tasks
    tasks = [
        ("tower", "Floor 5 slab shuttering", "Suresh", "in_progress", -1, ["Plywood", "Props"], "Shuttering for the floor 5 slab, grid A-F."),
        ("tower", "Floor 5 slab reinforcement", "Manjunath", "pending", 2, ["Steel"], "Tie and inspect slab steel before the pour."),
        ("tower", "Floor 5 slab casting", "Ramesh", "pending", 3, ["Cement", "Sand", "Aggregate"], "M25 pour; needs 180 bags of cement on site."),
        ("tower", "Floor 4 blockwork", "Imran", "blocked", -3, ["AAC Blocks"], "Blocked: AAC blocks not delivered."),
        ("tower", "Basement waterproofing touch-up", "Lakshmi", "completed", -8, [], "Seal the leaks found after the monsoon inspection."),
        ("tower", "Lift shaft safety barricades", "Ramesh", "pending", -2, [], "Barricade open lift shafts on floors 3-5 (from safety report)."),
        ("plaza", "Retaining wall section 2 casting", "Kavya", "in_progress", 5, ["Cement", "Steel"], "Section 2 of the east retaining wall."),
        ("plaza", "Temporary power distribution", "Vijay", "completed", -6, [], "Install distribution boards for site power."),
        ("plaza", "Tower crane load test", "Anil", "pending", 1, [], "Monthly load test before lifting resumes."),
        ("plaza", "Steel column base plates", "Prakash", "pending", 9, ["Steel"], "Weld base plates for grid 1-4 columns."),
        ("plaza", "Dewatering pit cleaning", "Mohan", "pending", -4, [], "Clean and re-level the dewatering pits."),
    ]
    tid = {}
    for key, title, worker, status, due, materials, description in tasks:
        category = next(w[2] for w in workers if w[0] == worker)
        tid[title] = str((await db.tasks.insert_one(tagged({
            "title": title, "description": description, "project_id": pid[key], "assigned_worker_id": wid[worker], "assigned_category": category,
            "due_date": TODAY + timedelta(days=due, hours=17), "start_date": TODAY + timedelta(days=min(due, 0) - 4), "depends_on": [],
            "required_materials": materials, "status": status}))).inserted_id)
    await db.tasks.update_one({"_id": ObjectId(tid["Floor 5 slab casting"])}, {"$set": {"depends_on": [tid["Floor 5 slab shuttering"], tid["Floor 5 slab reinforcement"]]}})

    # ------------------------------------------------------------ vendors & procurement
    vendors = {
        "cement": ("Shree Cement Traders", "Ravi Hegde", "29AAFCS4821K1Z3", ["Cement"], 4.4, "Peenya Industrial Area, Bengaluru"),
        "steel": ("Bharat Steel Distributors", "Arvind Joshi", "27AABCB7712M1Z8", ["Steel", "Binding wire"], 4.1, "Bhiwandi, Maharashtra"),
        "sand": ("Kaveri Sand and Aggregates", "Naveen Kumar", "29AAGFK3390P1Z1", ["Sand", "Aggregate", "AAC Blocks"], 3.6, "Hoskote, Bengaluru"),
    }
    vid = {}
    for key, (name, contact, gstin, materials, rating, address) in vendors.items():
        vid[key] = str((await db.vendors.insert_one(tagged({"vendor_name": name, "contact_person": contact, "phone": f"080-4100{len(vid):04d}",
                                                            "email": f"sales.{key}@example.com", "address": address, "gst_number": gstin,
                                                            "pan_number": gstin[2:12], "materials_supplied": materials, "rating": rating, "status": "active"}))).inserted_id)

    async def request(key, material, unit, qty, status, required_in, priority, vendor=None, extra=None):
        doc = tagged({"project": projects[key]["name"], "project_id": pid[key], "material_name": material, "material_id": None, "unit": unit,
                      "quantity": float(qty), "required_date": TODAY + timedelta(days=required_in), "priority": priority, "remarks": None,
                      "request_id": await next_code(db, "material_requests", "MR"), "status": status, "requested_by": str(engineer.get("_id", actor)),
                      "created_at": ago(25 - required_in if required_in < 25 else 3)})
        if status != "pending":
            doc.update(approved_at=ago(18), approved_by=actor, approval_comments="Approved for the current pour.")
        if vendor:
            doc.update(vendor_id=vid[vendor], assigned_vendor_id=vid[vendor], vendor_name=vendors[vendor][0], vendor_assigned_at=ago(16),
                       vendor_assigned_by=actor, vendor_response="accepted" if status not in {"vendor_assigned"} else None,
                       vendor_response_date=ago(15) if status != "vendor_assigned" else None)
        doc.update(extra or {})
        result = await db.material_requests.insert_one(doc)
        return str(result.inserted_id), doc

    async def order(req_id, req, vendor, unit_price, rate, status, expected_in):
        po = tagged({"request_id": req_id, "vendor_id": vid[vendor], "project": req["project"], "project_id": req["project_id"],
                     "materials": req["material_name"], "material_id": None, "quantity": req["quantity"], "unit_price": float(unit_price),
                     "expected_delivery_date": TODAY + timedelta(days=expected_in), "status": status,
                     "po_number": await next_code(db, "purchase_orders", "PO"), "created_at": ago(14)})
        po.update(price_order(req["quantity"], unit_price, gst_rate=rate, vendor_gstin=vendors[vendor][2]))
        po_id = str((await db.purchase_orders.insert_one(po)).inserted_id)
        await db.material_requests.update_one({"_id": ObjectId(req_id)}, {"$set": {"po_number": po["po_number"], "purchase_order_id": po_id}})
        return po_id, po

    await request("tower", "AAC Blocks", "Nos", 4000, "pending", 6, "high")
    await request("plaza", "Binding wire", "kg", 250, "approved", 10, "medium")
    await request("tower", "Sand", "cft", 1200, "vendor_assigned", 4, "medium", vendor="sand")
    cement_req, cement = await request("tower", "Cement", "bags", 200, "po_generated", -4, "high", vendor="cement")
    steel_req, steel = await request("plaza", "Steel", "MT", 12, "delivered", -12, "high", vendor="steel")
    agg_req, agg = await request("plaza", "Aggregate", "cft", 900, "po_generated", 8, "low", vendor="sand")

    cement_po_id, cement_po = await order(cement_req, cement, "cement", 380, 28, "accepted", -4)  # 4 days overdue
    steel_po_id, steel_po = await order(steel_req, steel, "steel", 61500, 18, "delivered", -12)
    agg_po_id, agg_po = await order(agg_req, agg, "sand", 62, 5, "sent", 8)

    deliveries = [
        (cement_po_id, cement_po, 120, "accepted", "passed", 6, "KA-50-AB-2231", "First lot, 120 of 200 bags."),
        (cement_po_id, cement_po, 30, "delivered", "pending", 1, "KA-50-AB-2231", "Arrived yesterday; awaiting inspection."),
        (steel_po_id, steel_po, 12, "accepted", "passed", 13, "MH-04-KL-9083", "Full quantity with mill test certificates."),
    ]
    for po_id, po, qty, status, quality, days, vehicle, remarks in deliveries:
        await db.deliveries.insert_one(tagged({"purchase_order_id": po_id, "po_number": po["po_number"], "vendor_id": po["vendor_id"],
                                               "material": po["materials"], "quantity_received": float(qty), "quality_status": quality,
                                               "delivery_date": ago(days), "dispatch_date": ago(days + 1), "vehicle_number": vehicle,
                                               "tracking_number": f"TRK{qty}{days}", "remarks": remarks, "status": status, "created_at": ago(days)}))

    steel_invoice = tagged({"purchase_order_id": steel_po_id, "invoice_number": "BSD/2026/0418", "invoice_date": ago(11), "amount": steel_po["subtotal"],
                            "gst": steel_po["gst"], "gst_rate": 18.0, "supply_type": steel_po["supply_type"], "cgst": steel_po["cgst"], "sgst": steel_po["sgst"],
                            "igst": steel_po["igst"], "attachment_url": None, "vendor_id": vid["steel"], "status": "approved", "payment_status": "paid",
                            "verification_comments": "Matches PO and full delivery.", "created_at": ago(11)})
    steel_invoice_id = str((await db.invoices.insert_one(steel_invoice)).inserted_id)
    # Billed for 180 bags while only 120 are accepted: the 3-way match flags it.
    over = 180 * 380.0
    await db.invoices.insert_one(tagged({"purchase_order_id": cement_po_id, "invoice_number": "SCT/1127", "invoice_date": ago(2), "amount": over,
                                         "gst": round(over * 0.28, 2), "gst_rate": 28.0, "supply_type": cement_po["supply_type"], "cgst": None, "sgst": None,
                                         "igst": None, "attachment_url": None, "vendor_id": vid["cement"], "status": "pending", "payment_status": "pending",
                                         "created_at": ago(2)}))
    await db.payments.insert_one(tagged({"invoice_id": steel_invoice_id, "vendor_id": vid["steel"], "purchase_order_id": steel_po_id,
                                         "amount": steel_po["total_cost"], "status": "paid", "paid_at": ago(8), "remarks": "NEFT UTR DEMO0418",
                                         "invoice_number": steel_invoice["invoice_number"], "po_number": steel_po["po_number"],
                                         "vendor_name": vendors["steel"][0], "created_at": ago(8)}))

    # ------------------------------------------------------------ safety & suggestions
    reporter = str(engineer.get("_id", actor))
    safety = [
        ("tower", "hazard", "high", "Open lift shafts without barricades", "Lift shafts on floors 3 to 5 are open on two sides with no barricade or toe board. Workers pass close by while carrying shuttering material.",
         "Floors 3-5, lift core", "Warned the crew and placed a temporary rope.", "action_required", False, 4),
        ("tower", "near_miss", "medium", "Cement bags stored in the rain", "The vendor truck was delayed by a transport strike, and 20 bags were unloaded late and left uncovered overnight. Some bags got wet and hardened.",
         "Ground floor store", "Moved the dry bags under the shed and separated the wet ones.", "under_review", False, 6),
        ("plaza", "incident", "medium", "Minor hand injury during rebar cutting", "A helper's glove caught on a rebar end while feeding the bar cutting machine. First aid given; no lost time.",
         "East retaining wall", "First aid given; machine guard checked.", "resolved", True, 9),
        ("plaza", "inspection", "low", "Weekly scaffold inspection", "Cuplock scaffold on the east wall inspected. Two missing toe boards replaced; tags updated.",
         "East wall scaffold", None, "closed", False, 12),
        ("tower", "hazard", "urgent", "Exposed live cable near the batching area", "A temporary power cable is lying in standing water near the batching area with damaged insulation.",
         "Batching area", "Area cordoned off; electrician called.", "open", False, 0.2),
    ]
    first_report = None
    for key, kind, severity, title, description, location, action, status, anonymous, days in safety:
        history = [{"status": "open", "at": ago(days)}] + ([{"status": status, "at": ago(days * 0.5)}] if status != "open" else [])
        report_id = str((await db.safety_reports.insert_one(tagged({
            "report_type": kind, "severity": severity, "title": title, "description": description, "project_id": pid[key], "location": location,
            "occurred_at": ago(days), "anonymous": anonymous, "evidence_ids": [], "immediate_action_taken": action, "reporter_id": reporter,
            "status": status, "history": history, "escalated_at": None, "created_at": ago(days)}))).inserted_id)
        first_report = first_report or report_id
    await db.corrective_actions.insert_one(tagged({
        "title": "Install rigid barricades and toe boards at lift shafts", "description": "Fix 1 m high rigid barricades with toe boards on all open lift-shaft sides, floors 3-5.",
        "assignee_id": reporter, "due_date": TODAY + timedelta(days=2), "safety_report_id": first_report, "project_id": pid["tower"], "status": "in_progress",
        "assigned_by": actor, "history": [{"status": "assigned", "by": actor, "at": ago(3)}, {"status": "in_progress", "by": reporter, "at": ago(2)}], "created_at": ago(3)}))

    suggestions = [
        ("tower", "Covered cement store near the hoist", "Cement is stored 60 m from the hoist, so bags are carried twice and get wet in rain.",
         "Build a raised, covered store next to the material hoist.", "material_wastage", "Fewer wet bags and about 2 labour hours saved per pour.", "under_review"),
        ("plaza", "Rebar cutting schedule from BBS software", "Bars are cut by hand from drawings, causing offcut waste of around 6 percent.",
         "Generate a cutting schedule from the bar bending schedule to reduce offcuts.", "cost_reduction", "Less steel wastage.", "approved_for_trial"),
        ("tower", "Toolbox talk before every slab pour", "Night pours start without a safety briefing.", "Hold a 10 minute toolbox talk before each pour.",
         "safety_improvement", "Fewer near misses during pours.", "submitted"),
    ]
    for key, title, problem, solution, category, benefit, status in suggestions:
        await db.suggestions.insert_one(tagged({"title": title, "problem": problem, "proposed_solution": solution, "category": category,
                                                "project_id": pid[key], "expected_benefit": benefit, "evidence_ids": [], "submitted_by": reporter,
                                                "submitter_role": "site_engineer", "status": status,
                                                "history": [{"status": "submitted", "by": reporter, "at": ago(7)}], "measured_outcomes": [], "created_at": ago(7)}))

    # ------------------------------------------------------------ saved reports (real content from the records above)
    reports = 0
    if admin.get("_id"):
        from app.modules.intelligence import reports as report_builder
        from app.modules.intelligence.data import build_scope

        admin_user = await db.users.find_one({"_id": admin["_id"]})
        scope = await build_scope(db, admin_user)
        for report_type, key in (("weekly_project", "tower"), ("procurement", None), ("safety_actions", None)):
            try:
                report = await report_builder.generate_report(db, scope, report_type, pid[key] if key else None)
            except Exception as error:  # a report that cannot be built is skipped, not fatal
                print(f"skipped {report_type} report: {error}")
                continue
            await db.generated_reports.insert_one({"seed": TAG, "owner_id": str(admin["_id"]), "type": report_type, "project_id": pid[key] if key else None,
                                                   "report": report, "ai_summary": None, "client_visible": False, "created_at": UTC_NOW})
            reports += 1

    return {name: await db[name].count_documents({"seed": TAG}) for name in COLLECTIONS} | {"generated_reports": reports}


async def main(drop: bool) -> None:
    db = AsyncIOMotorClient(settings.mongodb_url)[settings.mongodb_db_name]
    counts = await (remove(db) if drop else seed(db))
    verb = "Removed" if drop else "Demo data now in"
    print(f"{verb} database '{settings.mongodb_db_name}':")
    for name, count in counts.items():
        print(f"  {name:22} {count}")
    if not drop:
        print("Agent mode: press 'Rebuild search index' so the agents can search the new reports.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--remove", action="store_true", help="delete only the demo data this script added")
    asyncio.run(main(parser.parse_args().remove))
