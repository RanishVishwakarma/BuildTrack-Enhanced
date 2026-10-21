"""The seven canonical BuildTrack roles.

Every role value read from the database or a request goes through
`normalize_role`, so legacy spellings already stored in `users`
("Administrator", "manager", "Project Manager", "engineer", ...) resolve to one
canonical identifier. Unknown values resolve to None and are denied.

Store Manager and Finance are not roles. Their duties are permissions
(see app.core.permissions) that an admin grants to individual users.
"""

ADMIN = "admin"
PROJECT_MANAGER = "projectmanager"
SITE_ENGINEER = "siteengineer"
WORKER = "worker"
VENDOR = "vendor"
CLIENT = "client"
CONTRACTOR = "contractor"

CANONICAL_ROLES = (ADMIN, PROJECT_MANAGER, SITE_ENGINEER, WORKER, VENDOR, CLIENT, CONTRACTOR)

# Roles anyone may choose at public sign-up. Admin and vendor accounts are
# created by an administrator only.
SELF_REGISTER_ROLES = (PROJECT_MANAGER, SITE_ENGINEER, WORKER, CLIENT, CONTRACTOR)
# Staff roles can create projects or manage people and orders, so a self-registered
# account stays "pending" until an administrator approves it. Workers and clients
# start active: they see nothing until a manager links or grants access.
APPROVAL_REQUIRED_ROLES = (PROJECT_MANAGER, SITE_ENGINEER, CONTRACTOR)

_ALIASES = {
    "admin": ADMIN,
    "administrator": ADMIN,
    "projectmanager": PROJECT_MANAGER,
    "project manager": PROJECT_MANAGER,
    "manager": PROJECT_MANAGER,
    "pm": PROJECT_MANAGER,
    "siteengineer": SITE_ENGINEER,
    "site engineer": SITE_ENGINEER,
    "engineer": SITE_ENGINEER,
    "worker": WORKER,
    "vendor": VENDOR,
    "supplier": VENDOR,
    "client": CLIENT,
    "contractor": CONTRACTOR,
    "subcontractor": CONTRACTOR,
}

# Legacy role values that were duties, not roles. They are deliberately not
# mapped (deny by default); the role migration reports such users so an admin
# picks one of the seven roles and grants these permissions explicitly.
LEGACY_DUTY_PERMISSIONS = {
    "store manager": ("inventory.adjust.assigned", "procurement.delivery.receive"),
    "finance": ("procurement.payment.record", "budget.read.assigned"),
}


def _key(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


def normalize_role(value) -> str | None:
    """Return the canonical role for a stored or submitted value, or None."""
    if not isinstance(value, str):
        return None
    return _ALIASES.get(_key(value))


def legacy_duty(value) -> str | None:
    """Name of a legacy duty role (store manager, finance), if `value` is one."""
    if not isinstance(value, str):
        return None
    key = _key(value)
    return key if key in LEGACY_DUTY_PERMISSIONS else None


def role_label(role: str | None) -> str:
    return {
        ADMIN: "Administrator",
        PROJECT_MANAGER: "Project Manager",
        SITE_ENGINEER: "Site Engineer",
        WORKER: "Worker",
        VENDOR: "Vendor",
        CLIENT: "Client",
        CONTRACTOR: "Contractor",
    }.get(role or "", "Unknown")
