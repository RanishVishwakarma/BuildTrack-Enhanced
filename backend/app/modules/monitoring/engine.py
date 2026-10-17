"""Background monitoring: detect conditions, alert the responsible people,
escalate what is not acknowledged, and resolve alerts whose cause is gone.

Reliability:
  * A lease in `job_locks` stops two app instances running the same job.
  * Every run is recorded in `job_runs` with per-rule errors; one failing rule
    does not stop the others.
  * Alerts are keyed by (rule, record, recipient). Re-detecting a condition only
    refreshes `last_seen_at`; the notification is sent once.
  * Escalation uses a conditional update, so a retried or concurrent run cannot
    escalate (or call) twice.
  * State lives in MongoDB, so a restart resumes from the stored alerts.
"""

import logging
import re
from datetime import timedelta
from uuid import uuid4

from bson import ObjectId

from app.core.audit import record_audit
from app.core.config import settings
from app.core.permissions import PERMISSIONS
from app.modules.intelligence import materials, risk
from app.modules.intelligence.common import is_done, iso, norm_text, parse_dt, utcnow
from app.modules.intelligence.data import Scope, procurement_status, project_milestones
from app.modules.notifications.db import create_notification

logger = logging.getLogger(__name__)

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}
LOCK_ID = "monitoring"
LOCK_SECONDS = 600

# Internal service identity used only inside this module to evaluate every
# project. It never authenticates a request and is not stored as a user.
SYSTEM_USER = {"_id": "system", "role": "admin", "full_name": "BuildTrack monitoring", "_permissions": set(PERMISSIONS)}


async def system_scope(db) -> Scope:
    projects = await db.projects.find({}).to_list(5000)
    return Scope(user=SYSTEM_USER, project_ids=None, projects=projects)


async def project_managers(db, project_id: str | None) -> list[str]:
    if not project_id:
        return []
    rows = await db.user_project_access.find({"project_id": str(project_id), "active": {"$ne": False}}).to_list(200)
    ids = [ObjectId(r["user_id"]) for r in rows if ObjectId.is_valid(r["user_id"])]
    if not ids:
        return []
    managers = await db.users.find({"_id": {"$in": ids}, "role": "projectmanager", "status": {"$regex": "^active$", "$options": "i"}}, {"_id": 1}).to_list(50)
    return [str(m["_id"]) for m in managers]


async def admins(db) -> list[str]:
    rows = await db.users.find({"role": "admin", "status": {"$regex": "^active$", "$options": "i"}}, {"_id": 1}).to_list(50)
    return [str(r["_id"]) for r in rows]


async def users_for_worker(db, worker_id: str | None) -> list[str]:
    if not worker_id or not ObjectId.is_valid(str(worker_id)):
        return []
    worker = await db.workers.find_one({"_id": ObjectId(str(worker_id))}, {"email": 1})
    if not worker or not worker.get("email"):
        return []
    user = await db.users.find_one({"email": {"$regex": f"^{re.escape(worker['email'])}$", "$options": "i"}, "status": {"$regex": "^active$", "$options": "i"}}, {"_id": 1})
    return [str(user["_id"])] if user else []


class AlertSink:
    """Collects alerts for one run and writes them idempotently."""

    def __init__(self, db, run_id: str):
        self.db = db
        self.run_id = run_id
        self.seen: set[str] = set()
        self.rules_evaluated: set[str] = set()
        self.created = 0

    async def raise_alert(self, *, rule: str, resource_type: str, resource_id: str, project_id: str | None, recipients: list[str],
                          title: str, message: str, severity: str) -> None:
        now = utcnow()
        if not recipients and severity in {"high", "critical"}:
            recipients = await admins(self.db)  # nobody assigned: serious issues go to administrators
        for user_id in dict.fromkeys(recipients):
            key = f"{rule}:{resource_id}:{user_id}"
            self.seen.add(key)
            existing = await self.db.alerts.find_one({"dedup_key": key, "status": "open"})
            if existing:
                update = {"last_seen_at": now, "message": message, "title": title}
                if SEVERITY_RANK[severity] > existing.get("severity_rank", 0):
                    update.update({"severity": severity, "severity_rank": SEVERITY_RANK[severity]})
                await self.db.alerts.update_one({"_id": existing["_id"]}, {"$set": update})
                continue
            notification = await create_notification(self.db, {
                "user_id": user_id, "title": title, "message": message, "type": "warning" if severity in {"low", "medium"} else "error",
                "category": "monitoring", "entity_type": resource_type, "entity_id": resource_id,
            })
            await self.db.alerts.insert_one({
                "dedup_key": key, "rule": rule, "resource_type": resource_type, "resource_id": resource_id, "project_id": project_id,
                "user_id": user_id, "title": title, "message": message, "severity": severity, "severity_rank": SEVERITY_RANK[severity],
                "status": "open", "escalation_level": 0, "created_at": now, "last_seen_at": now, "acknowledged_at": None,
                "notification_id": str(notification["_id"]) if notification else None, "run_id": self.run_id,
            })
            self.created += 1


async def _rule_overdue_tasks(db, scope, sink: AlertSink):
    now = utcnow()
    for task in await db.tasks.find({}).to_list(20000):
        due = parse_dt(task.get("due_date"))
        if not due or due >= now or is_done(task.get("status")):
            continue
        days = (now - due).days
        recipients = await users_for_worker(db, task.get("assigned_worker_id")) + await project_managers(db, task.get("project_id"))
        await sink.raise_alert(rule="overdue_task", resource_type="task", resource_id=str(task["_id"]), project_id=task.get("project_id"), recipients=recipients,
                               title=f"Task overdue: {task.get('title')}", message=f"'{task.get('title')}' was due {iso(due)[:10]} ({days} day(s) ago).",
                               severity="critical" if days > 7 else ("high" if days > 2 else "medium"))


async def _rule_milestones(db, scope, sink: AlertSink):
    now = utcnow()
    for project in scope.projects:
        if is_done(project.get("status")):
            continue
        pid = str(project["_id"])
        for milestone in await project_milestones(db, project):
            due = parse_dt(milestone["due_date"])
            if not due or is_done(milestone["status"]):
                continue
            if due < now:
                await sink.raise_alert(rule="overdue_milestone", resource_type="milestone", resource_id=milestone["id"], project_id=pid, recipients=await project_managers(db, pid),
                                       title=f"Milestone overdue: {milestone['title']}", message=f"{project.get('name')}: '{milestone['title']}' was due {iso(due)[:10]}.",
                                       severity="high" if (now - due).days >= 7 else "medium")
            elif due <= now + timedelta(days=3):
                await sink.raise_alert(rule="upcoming_milestone", resource_type="milestone", resource_id=milestone["id"], project_id=pid, recipients=await project_managers(db, pid),
                                       title=f"Milestone due soon: {milestone['title']}", message=f"{project.get('name')}: '{milestone['title']}' is due {iso(due)[:10]}.", severity="low")


async def _rule_shortages(db, scope, sink: AlertSink):
    now = utcnow()
    forecast = await materials.material_forecast(db, scope, horizon_days=21)
    for row in forecast["shortages"]:
        needed = parse_dt(row["next_required_date"])
        projects = {d.get("project") for d in row["demand"]}
        for project in scope.projects:
            if project.get("name") not in projects:
                continue
            await sink.raise_alert(rule="material_shortage", resource_type="inventory_item", resource_id=row["item_id"], project_id=str(project["_id"]),
                                   recipients=await project_managers(db, str(project["_id"])),
                                   title=f"Material shortage: {row['material']}", message=f"Projected shortfall {row['projected_shortfall']:g} {row['unit'] or ''} ({row['shortfall_formula']}).",
                                   severity="high" if needed and needed <= now + timedelta(days=7) else "medium")


async def _rule_procurement(db, scope, sink: AlertSink):
    now = utcnow()
    status = await procurement_status(db, scope)
    by_name = {norm_text(p.get("name")): str(p["_id"]) for p in scope.projects}
    for order in status["overdue_deliveries"]:
        pid = by_name.get(norm_text(order["project"]))
        await sink.raise_alert(rule="delayed_delivery", resource_type="purchase_order", resource_id=order["id"], project_id=pid, recipients=await project_managers(db, pid),
                               title=f"Delivery late: {order['po_number']}", message=f"{order['materials']} for {order['project']} was expected {(order['expected_delivery_date'] or '')[:10]} ({order['days_late']} day(s) late).",
                               severity="critical" if order["days_late"] >= 14 else ("high" if order["days_late"] >= 7 else "medium"))
    for request in status["pending_approvals"]:
        record = await db.material_requests.find_one({"_id": ObjectId(request["id"])}) if ObjectId.is_valid(request["id"]) else None
        created = parse_dt(record.get("created_at")) if record else None
        if created and (now - created).days >= 2:
            pid = (record.get("project_id") if record else None) or by_name.get(norm_text(request["project"]))
            await sink.raise_alert(rule="pending_approval", resource_type="material_request", resource_id=request["id"], project_id=pid, recipients=await project_managers(db, pid),
                                   title=f"Approval waiting: {request['request_id'] or request['material']}", message=f"{request['material']} for {request['project']} has waited {(now - created).days} day(s) for approval.", severity="low")


async def _rule_safety(db, scope, sink: AlertSink):
    now = utcnow()
    for action in await db.corrective_actions.find({"status": {"$nin": ["closed", "cancelled", "verified"]}}).to_list(10000):
        due = parse_dt(action.get("due_date"))
        if due and due < now:
            recipients = ([action["assignee_id"]] if action.get("assignee_id") else []) + await project_managers(db, action.get("project_id"))
            await sink.raise_alert(rule="overdue_corrective_action", resource_type="corrective_action", resource_id=str(action["_id"]), project_id=action.get("project_id"), recipients=recipients,
                                   title=f"Corrective action overdue: {action.get('title')}", message=f"Due {iso(due)[:10]}; status {action.get('status')}.", severity="high")
    for report in await db.safety_reports.find({"severity": "urgent", "status": {"$nin": ["closed", "resolved"]}}).to_list(5000):
        created = parse_dt(report.get("created_at"))
        if created and (now - created) >= timedelta(hours=24):
            await sink.raise_alert(rule="urgent_safety_unresolved", resource_type="safety_report", resource_id=str(report["_id"]), project_id=report.get("project_id"),
                                   recipients=await project_managers(db, report.get("project_id")) or await admins(db),
                                   title=f"Urgent safety report still open: {report.get('title')}", message="Opened more than 24 hours ago and not yet resolved.", severity="critical")


async def _rule_risks(db, scope, sink: AlertSink):
    summary = await risk.run_risk_assessment(db, scope, persist=True)
    for project in summary["projects"]:
        for finding in project["findings"]:
            if finding["level"] not in {"high", "critical"}:
                continue
            record = await db.risk_assessments.find_one({"project_id": project["project_id"], "rule": finding["rule"]})
            if not record or record.get("review_status") in {"resolved", "dismissed"}:
                continue
            recipients = [project["responsible_user_id"]] if project["responsible_user_id"] else await project_managers(db, project["project_id"])
            await sink.raise_alert(rule="project_risk", resource_type="risk_assessment", resource_id=str(record["_id"]), project_id=project["project_id"], recipients=recipients,
                                   title=f"{finding['level'].title()} {finding['category']} risk: {project['project']}", message=finding["factors"][0], severity=finding["level"])


RULES = [
    ("overdue_task", _rule_overdue_tasks),
    ("milestones", _rule_milestones),
    ("material_shortage", _rule_shortages),
    ("procurement", _rule_procurement),
    ("safety", _rule_safety),
    ("project_risk", _rule_risks),
]
RULE_KEYS = {
    "overdue_task": ["overdue_task"], "milestones": ["overdue_milestone", "upcoming_milestone"], "material_shortage": ["material_shortage"],
    "procurement": ["delayed_delivery", "pending_approval"], "safety": ["overdue_corrective_action", "urgent_safety_unresolved"], "project_risk": ["project_risk"],
}


async def escalate(db) -> int:
    """Escalate high/critical alerts left unacknowledged past the threshold."""
    cutoff = utcnow() - timedelta(minutes=settings.escalation_after_minutes)
    escalated = 0
    candidates = await db.alerts.find({"status": "open", "acknowledged_at": None, "escalation_level": 0, "severity": {"$in": ["high", "critical"]}, "created_at": {"$lte": cutoff}}).to_list(1000)
    for alert in candidates:
        claimed = await db.alerts.update_one({"_id": alert["_id"], "escalation_level": 0}, {"$set": {"escalation_level": 1, "escalated_at": utcnow()}})
        if claimed.modified_count != 1:
            continue  # another run already escalated it
        targets = [u for u in await project_managers(db, alert.get("project_id")) if u != alert["user_id"]] or [u for u in await admins(db) if u != alert["user_id"]]
        for user_id in targets:
            await create_notification(db, {"user_id": user_id, "title": f"Escalated: {alert['title']}", "message": f"Not acknowledged within {settings.escalation_after_minutes} minutes. {alert['message']}",
                                           "type": "error", "category": "escalation", "entity_type": alert["resource_type"], "entity_id": alert["resource_id"]})
        if alert["severity"] == "critical":
            from app.modules.voice import service as voice

            await voice.queue_call_for_alert(db, alert)
        escalated += 1
    return escalated


async def acquire_lock(db, owner: str) -> bool:
    now = utcnow()
    try:
        result = await db.job_locks.update_one(
            {"_id": LOCK_ID, "$or": [{"expires_at": {"$lte": now}}, {"owner": owner}]},
            {"$set": {"owner": owner, "expires_at": now + timedelta(seconds=LOCK_SECONDS)}},
            upsert=True,
        )
        return result.modified_count == 1 or result.upserted_id is not None
    except Exception:  # duplicate key: another instance holds a live lease
        return False


async def release_lock(db, owner: str) -> None:
    await db.job_locks.delete_one({"_id": LOCK_ID, "owner": owner})


async def run_monitoring(db, trigger: str = "schedule", actor: dict | None = None) -> dict:
    lease_owner = uuid4().hex
    started = utcnow()
    if not await acquire_lock(db, lease_owner):
        run = {"job": "monitoring", "trigger": trigger, "status": "skipped", "reason": "another run is in progress", "started_at": started, "finished_at": utcnow()}
        await db.job_runs.insert_one(run)
        return run
    run_id = (await db.job_runs.insert_one({"job": "monitoring", "trigger": trigger, "status": "running", "started_at": started})).inserted_id
    sink = AlertSink(db, str(run_id))
    errors = {}
    try:
        scope = await system_scope(db)
        for name, rule in RULES:
            try:
                await rule(db, scope, sink)
                sink.rules_evaluated.update(RULE_KEYS[name])
            except Exception as error:  # isolate failing rules
                logger.exception("Monitoring rule %s failed", name)
                errors[name] = f"{type(error).__name__}: {error}"
        # Resolve alerts whose condition was evaluated and is no longer present.
        resolved = 0
        if sink.rules_evaluated:
            stale = await db.alerts.find({"status": "open", "rule": {"$in": list(sink.rules_evaluated)}}, {"dedup_key": 1}).to_list(50000)
            ids = [a["_id"] for a in stale if a["dedup_key"] not in sink.seen]
            if ids:
                result = await db.alerts.update_many({"_id": {"$in": ids}}, {"$set": {"status": "resolved", "resolved_at": utcnow(), "resolution": "condition no longer detected"}})
                resolved = result.modified_count
                await db.voice_calls.update_many({"alert_id": {"$in": [str(i) for i in ids]}, "status": "queued"}, {"$set": {"status": "cancelled", "reason": "alert resolved"}})
        recommendations = 0
        try:
            from app.modules.actions.service import generate_from_engines

            async def responsible_manager(pid):
                managers = await project_managers(db, pid)
                return managers[0] if managers else None

            recommendations = await generate_from_engines(db, scope, responsible_manager)
        except Exception as error:
            logger.exception("Recommendation generation failed")
            errors["recommendations"] = f"{type(error).__name__}: {error}"
        escalated = 0
        try:
            escalated = await escalate(db)
        except Exception as error:
            logger.exception("Escalation failed")
            errors["escalation"] = f"{type(error).__name__}: {error}"
        status = "partial" if errors else "success"
        summary = {"status": status, "alerts_created": sink.created, "alerts_resolved": resolved, "alerts_escalated": escalated, "recommendations_created": recommendations, "rule_errors": errors, "finished_at": utcnow()}
        await db.job_runs.update_one({"_id": run_id}, {"$set": summary})
        if actor:
            await record_audit(db, "monitoring.run", actor=actor, resource_type="job_run", resource_id=str(run_id), details={"status": status})
        return {"_id": run_id, "job": "monitoring", "trigger": trigger, "started_at": started, **summary}
    except Exception as error:
        logger.exception("Monitoring run failed")
        await db.job_runs.update_one({"_id": run_id}, {"$set": {"status": "failed", "error": f"{type(error).__name__}: {error}", "finished_at": utcnow()}})
        raise
    finally:
        await release_lock(db, lease_owner)
