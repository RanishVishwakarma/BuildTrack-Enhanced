"""Permission registry and authorization dependencies.

Authorization is permission-based and deny-by-default:

* Each canonical role has a default permission set (ROLE_PERMISSIONS).
* An admin can grant extra permissions to an individual user (`users.permissions`)
  or revoke defaults (`users.revoked_permissions`), e.g. to give one site
  engineer the store-manager duty `procurement.delivery.receive`.
* Only identifiers listed in PERMISSIONS count; anything else is ignored.

A permission says what kind of action a user may take. Which records they may
take it on is a separate check (app.core.access).
"""

from fastapi import Depends, HTTPException, status

from app.core import roles

PERMISSIONS: dict[str, str] = {
    # Users and administration
    "users.read": "View user accounts",
    "users.create": "Create user, vendor and client accounts",
    "users.update": "Edit user accounts and status",
    "users.disable": "Disable or remove user accounts",
    "users.roles.assign": "Change roles and grant permissions",
    "audit_logs.read": "Read the audit log",
    # Projects
    "projects.read.all": "Read every project in the company",
    "projects.read.assigned": "Read assigned projects",
    "projects.create": "Create projects",
    "projects.update.assigned": "Edit assigned projects and milestones",
    "projects.access.manage": "Assign users to projects",
    "records.delete": "Delete records (projects, tasks, workers, documents, inventory)",
    # Tasks
    "tasks.read.assigned": "Read tasks on assigned projects",
    "tasks.read.own": "Read tasks assigned to me",
    "tasks.assign": "Create and assign tasks",
    "tasks.update.assigned": "Update tasks on assigned projects",
    "tasks.update.own": "Update progress on my own tasks",
    # Workforce
    "workforce.read.assigned": "Read crew, allocations and attendance on assigned projects",
    "workforce.read.sensitive": "Read wages, salaries and payroll",
    "workforce.manage": "Manage workers, allocations, shifts, attendance and payroll",
    "workforce.attendance.manage": "Mark and correct attendance for workers on assigned projects",
    "workforce.shifts.assign": "Assign workers on assigned projects to shifts",
    "workforce.login.manage": "Create, link and reset worker logins",
    # Inventory and resources
    "inventory.read.assigned": "Read stock levels",
    "inventory.adjust.assigned": "Create inventory items and stock transactions",
    "resources.read.assigned": "Read equipment and resources",
    "resources.manage": "Manage equipment and resources",
    # Documents
    "documents.read.assigned": "Read project documents",
    "documents.manage": "Upload and edit project documents",
    # Procurement
    "procurement.read.assigned": "Read material requests, purchase orders, deliveries and invoices",
    "procurement.request.create": "Raise and edit material requests",
    "procurement.request.review": "Approve requests, assign vendors, create and send purchase orders",
    "procurement.vendor.manage": "Create and edit vendor records",
    "procurement.vendor.login.manage": "Create vendor portal logins and reset their passwords",
    "procurement.delivery.receive": "Record and verify deliveries into stock",
    "procurement.invoice.manage": "Create, verify and reject invoices",
    "procurement.payment.record": "Record payments against invoices",
    # Budget and reports
    "budget.read.assigned": "Read budgets and spend on assigned projects",
    "reports.read.assigned": "Read reports for assigned projects",
    "reports.generate": "Generate reports",
    "reports.export.assigned": "Export reports",
    # Notifications
    "notifications.read.own": "Read my notifications",
    "notifications.send.assigned": "Send notifications to project members",
    "reports.publish": "Approve reports for client visibility",
    "budget.forecast.read": "Read budget forecasts, variance and spend anomalies",
    # AI
    "ai.query": "Ask the AI Site Assistant",
    "ai.agent.use": "Use Agent mode (multi-agent assistant on the local model)",
    "ai.report.generate": "Generate AI reports",
    "ai.recommendation.review": "Review AI recommendations",
    "ai.recommendation.approve": "Approve or reject AI recommendations",
    # Monitoring, risk and alerts
    "risks.read.assigned": "Read project risk assessments",
    "risks.review": "Review and resolve risk assessments",
    "monitoring.run": "Run monitoring jobs on demand and read job history",
    # Construction progress evidence
    "evidence.upload": "Upload progress photographs and evidence",
    "evidence.read.assigned": "View progress evidence on assigned projects",
    "evidence.review": "Review progress evidence and AI observations",
    # Innovation hub
    "suggestions.create": "Submit improvement suggestions",
    "suggestions.read.own": "Read my own suggestions",
    "suggestions.review.assigned": "Review suggestions on assigned projects",
    "suggestions.assign": "Assign suggestions to an owner",
    "suggestions.approve": "Approve or reject suggestions",
    "suggestions.implement": "Record implementation and verified outcomes",
    # Safety
    "safety_reports.create": "Submit safety reports",
    "safety_reports.read.assigned": "Read safety reports on assigned projects",
    "safety_reports.review": "Review and classify safety reports",
    "safety_reports.identity.reveal": "Reveal the identity of an anonymous safety reporter",
    "safety_actions.assign": "Assign corrective actions",
    "safety_actions.update.own": "Update corrective actions assigned to me",
    "safety_actions.close": "Verify and close corrective actions",
    # Voice calls
    "voice_calls.receive": "Receive automated voice calls",
    "voice_calls.initiate.assigned": "Start automated calls for assigned projects",
    "voice_calls.logs.read.assigned": "Read call logs for assigned projects",
}

# Permissions never granted by a role default, not even to admin. They must be
# granted to an individual user deliberately (spec: reporter identities are
# exposed only with explicit authorization).
EXPLICIT_ONLY = {"safety_reports.identity.reveal"}

_COMMON = {"notifications.read.own", "ai.query", "suggestions.create", "suggestions.read.own"}
_SITE_STAFF = {"safety_reports.create", "safety_actions.update.own", "voice_calls.receive", "evidence.upload"}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    roles.ADMIN: set(PERMISSIONS) - EXPLICIT_ONLY,
    roles.PROJECT_MANAGER: _COMMON
    | {
        "workforce.attendance.manage",
        "workforce.shifts.assign",
        "ai.agent.use",
        "projects.read.assigned",
        "projects.create",
        "projects.update.assigned",
        "projects.access.manage",
        "tasks.read.assigned",
        "tasks.assign",
        "tasks.update.assigned",
        "workforce.read.assigned",
        "workforce.read.sensitive",
        "workforce.manage",
        "workforce.login.manage",
        "inventory.read.assigned",
        "inventory.adjust.assigned",
        "resources.read.assigned",
        "resources.manage",
        "documents.read.assigned",
        "documents.manage",
        "procurement.read.assigned",
        "procurement.request.create",
        "procurement.request.review",
        "procurement.vendor.manage",
        "procurement.vendor.login.manage",
        "procurement.delivery.receive",
        "budget.read.assigned",
        "reports.read.assigned",
        "reports.generate",
        "reports.export.assigned",
        "notifications.send.assigned",
        "ai.report.generate",
        "reports.publish",
        "budget.forecast.read",
        "ai.recommendation.review",
        "ai.recommendation.approve",
        "risks.read.assigned",
        "risks.review",
        "evidence.read.assigned",
        "evidence.review",
        "suggestions.review.assigned",
        "suggestions.assign",
        "suggestions.approve",
        "suggestions.implement",
        "safety_reports.read.assigned",
        "safety_reports.review",
        "safety_actions.assign",
        "safety_actions.close",
        "voice_calls.initiate.assigned",
        "voice_calls.logs.read.assigned",
    }
    | _SITE_STAFF,
    roles.SITE_ENGINEER: _COMMON
    | {
        # Hierarchy: site engineers manage workers on their projects (attendance,
        # shifts, tasks), but not pay, allocations or worker logins.
        "workforce.attendance.manage",
        "workforce.shifts.assign",
        "tasks.assign",
        "ai.agent.use",
        "projects.read.assigned",
        "tasks.read.assigned",
        "tasks.update.assigned",
        "workforce.read.assigned",
        "inventory.read.assigned",
        "resources.read.assigned",
        "documents.read.assigned",
        "procurement.read.assigned",
        "procurement.request.create",
        "procurement.delivery.receive",
        "reports.read.assigned",
        "risks.read.assigned",
        "evidence.read.assigned",
        "ai.recommendation.review",
        "safety_reports.read.assigned",
        "suggestions.implement",
    }
    | _SITE_STAFF,
    roles.CONTRACTOR: _COMMON
    | {
        "projects.read.assigned",
        "tasks.read.assigned",
        "tasks.update.own",
        "inventory.read.assigned",
        "documents.read.assigned",
        "procurement.request.create",
    }
    | _SITE_STAFF,
    roles.WORKER: _COMMON | _SITE_STAFF | {"projects.read.assigned", "tasks.read.own", "tasks.update.own"},
    # Clients see only reports an authorized user has published to them.
    roles.CLIENT: _COMMON | {"projects.read.assigned", "reports.read.assigned"},
    # Vendor portal routes are scoped by the vendor's own vendor_id.
    roles.VENDOR: set(_COMMON),
}


def _as_set(value) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {item for item in value if isinstance(item, str)}
    return set()


def effective_permissions(user: dict | None) -> set[str]:
    """Role defaults plus per-user grants, minus per-user revocations."""
    if not user:
        return set()
    role = roles.normalize_role(user.get("role"))
    if role is None:
        return set()
    granted = ROLE_PERMISSIONS.get(role, set()) | _as_set(user.get("permissions"))
    granted -= _as_set(user.get("revoked_permissions"))
    return {perm for perm in granted if perm in PERMISSIONS}


def has_permission(user: dict | None, *permissions: str) -> bool:
    """True when the user holds at least one of `permissions`."""
    held = user.get("_permissions") if user and "_permissions" in user else effective_permissions(user)
    return any(perm in held for perm in permissions)


def ensure_permission(user: dict | None, *permissions: str) -> None:
    """Raise 403 unless the user holds at least one of `permissions`."""
    if not has_permission(user, *permissions):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")


def require_permission(*permissions: str):
    """FastAPI dependency: the current user must hold one of `permissions`."""
    unknown = [perm for perm in permissions if perm not in PERMISSIONS]
    if unknown:
        raise ValueError(f"Unknown permission(s): {unknown}")

    from app.core.security import get_current_user

    async def checker(current_user=Depends(get_current_user)):
        ensure_permission(current_user, *permissions)
        return current_user

    return checker
