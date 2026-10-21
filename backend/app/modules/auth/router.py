import re
from datetime import datetime, timedelta
from secrets import token_urlsafe
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.core.audit import record_audit
from app.core.config import settings
from app.core.email import send_email
from app.core.permissions import effective_permissions, ensure_permission
from app.core.roles import APPROVAL_REQUIRED_ROLES, CANONICAL_ROLES, SELF_REGISTER_ROLES
from app.core.roles import normalize_role as normalize_canonical_role
from app.core.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

SENSITIVE_USER_FIELDS = {"password_hash", "password", "hashed_password", "password_reset_token_hash", "password_reset_expires_at"}
from app.db.mongodb import get_database
from app.modules.auth.db import (
    create_social_user,
    create_user,
    get_user_by_email,
    set_password_reset_token,
    update_password_and_clear_reset,
)
from app.modules.auth.models import User, UserCreate
from app.modules.notifications.db import create_notification

router = APIRouter()


# ============================================================
# REQUEST / RESPONSE MODELS
# ============================================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User
    worker_id: Optional[str] = None


class RegisterRequest(UserCreate):
    pass


class RegisterResponse(BaseModel):
    message: str
    user: User
    pending_approval: bool = False


class SocialLoginRequest(BaseModel):
    provider: str
    email: EmailStr
    full_name: str
    role: str = "worker"
    status: str = "active"


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetResponse(BaseModel):
    message: str
    reset_token: str | None = None


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    token: str
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    avatar_url: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


# ============================================================
# HELPERS
# ============================================================

def serialize_user(user: dict) -> User:
    """
    Convert MongoDB user document into the Pydantic User model.
    """
    # Never return credentials or internal authorization state.
    user_data = {key: value for key, value in user.items() if key not in SENSITIVE_USER_FIELDS and not key.startswith("_permissions")}
    canonical = normalize_canonical_role(user_data.get("role"))
    if canonical:
        user_data["role"] = canonical
    user_data.pop("stored_role", None)
    user_data["permissions"] = sorted(effective_permissions({**user, "role": canonical}))
    user_data.pop("revoked_permissions", None)

    if "_id" in user_data:
        user_data["_id"] = str(user_data["_id"])

    if not user_data.get("created_at"):
        user_data["created_at"] = datetime.utcnow()
    if not user_data.get("updated_at"):
        user_data["updated_at"] = datetime.utcnow()

    name_val = user_data.get("full_name") or user_data.get("name") or str(user_data.get("email", "")).split("@")[0]
    user_data["full_name"] = name_val
    user_data["name"] = name_val

    return User(**user_data)


def normalize_role(role: str | None) -> str:
    """
    Normalize roles so values like:
    Vendor, VENDOR, vendor -> vendor
    Project Manager -> project manager
    """
    return (role or "").strip().lower().replace("_", " ")


async def get_active_vendor(db, vendor_id: str):
    """
    Find an existing active Vendor document.

    Vendor login accounts must always point to an existing Vendor.
    """
    try:
        object_id = ObjectId(vendor_id)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid vendor_id",
        )

    vendor = await db.vendors.find_one({"_id": object_id})

    if not vendor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Linked vendor record does not exist",
        )

    if normalize_role(vendor.get("status")) != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Linked vendor record is not active",
        )

    return vendor


async def notify_admin_of_new_user(db, user: dict, role_name: str):
    """Notify all administrators when any new client, site engineer, worker, project manager, or user signs up, and send a welcome notification to the user."""
    try:
        user_id = str(user.get("_id", ""))
        user_name = user.get("name") or user.get("full_name") or str(user.get("email", "")).split("@")[0]
        user_email = user.get("email", "")
        formatted_role = role_name.title() if role_name else "User"

        # Find all administrators
        admins = await db.users.find({
            "$or": [
                {"role": {"$regex": "^admin", "$options": "i"}},
                {"role": "Administrator"},
                {"role": "admin"},
            ]
        }).to_list(50)

        # Notify each admin
        for admin in admins:
            admin_id = str(admin["_id"])
            if admin_id != user_id:
                await create_notification(db, {
                    "user_id": admin_id,
                    "title": "New User Registration",
                    "message": f"New user '{user_name}' ({user_email}) has signed up as {formatted_role}.",
                    "type": "info",
                    "category": "user_registration",
                    "entity_type": "user",
                    "entity_id": user_id,
                })

        # Send welcome notification to the new user from Admin
        await create_notification(db, {
            "user_id": user_id,
            "title": "Welcome to BuildTrack!",
            "message": f"Welcome {user_name}! Your account has been registered as {formatted_role}. Administrator has been notified.",
            "type": "success",
            "category": "welcome",
            "entity_type": "user",
            "entity_id": user_id,
        })
    except Exception as e:
        print(f"Error creating user registration notifications: {e}")


async def notify_admin_of_profile_change(db, user: dict, changes: list[str]):
    """Notify all administrators when a user modifies their account settings (name, email, password)"""
    try:
        user_id = str(user.get("_id", ""))
        user_name = user.get("name") or user.get("full_name") or str(user.get("email", "")).split("@")[0]
        user_email = user.get("email", "")
        role = (user.get("role") or "User").title()

        admins = await db.users.find({
            "$or": [
                {"role": {"$regex": "^admin", "$options": "i"}},
                {"role": "Administrator"},
                {"role": "admin"},
            ]
        }).to_list(50)

        change_summary = "; ".join(changes)
        full_msg = f"User '{user_name}' ({role}, {user_email}) modified account settings: {change_summary}."

        for admin in admins:
            admin_id = str(admin["_id"])
            await create_notification(db, {
                "user_id": admin_id,
                "title": "Account Settings Modified",
                "message": full_msg,
                "type": "warning" if any("password" in c.lower() or "email" in c.lower() for c in changes) else "info",
                "category": "security",
                "entity_type": "user",
                "entity_id": user_id,
            })
    except Exception as e:
        print(f"Failed to notify admins of profile change: {e}")


# ============================================================
# NORMAL USER REGISTRATION
# ============================================================

@router.post("/register", response_model=RegisterResponse)
async def register(
    request: RegisterRequest,
    db=Depends(get_database),
):
    """
    Public registration for normal users.

    IMPORTANT:
    Vendors are NOT allowed to self-register.

    A Vendor account can only be created by an Administrator
    through /auth/vendor-user.
    """

    requested_role = normalize_role(request.role)
    canonical_role = normalize_canonical_role(request.role)

    # --------------------------------------------------------
    # IMPORTANT SECURITY RULE
    # --------------------------------------------------------
    # Vendor registration is NEVER allowed through the public
    # registration endpoint.
    if requested_role == "vendor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Vendor self-registration is not allowed. "
                "An administrator must create the vendor account."
            ),
        )

    # --------------------------------------------------------
    # Check if email has been blocked/banned by Admin
    # --------------------------------------------------------
    banned = await db.banned_emails.find_one({"email": {"$regex": f"^{re.escape(request.email.strip())}$", "$options": "i"}})
    if banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been removed or blocked by an administrator. You cannot register. Please contact your system administrator at admin@buildtrack.com.",
        )

    # --------------------------------------------------------
    # Check duplicate email
    # --------------------------------------------------------
    existing_user = await get_user_by_email(db, request.email)

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Administrator accounts are created by an administrator, never through
    # public sign-up, and every account must hold one of the canonical roles.
    if canonical_role not in SELF_REGISTER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This role cannot be chosen at sign-up. Contact an administrator.",
        )
    request.role = canonical_role
    pending = canonical_role in APPROVAL_REQUIRED_ROLES
    request.status = "pending" if pending else "active"

    # --------------------------------------------------------
    # Create normal user
    # --------------------------------------------------------
    user = await create_user(db, request)
    await notify_admin_of_new_user(db, user, request.role)

    return RegisterResponse(
        message=("Account created. An administrator must approve it before you can sign in." if pending else "User registered successfully"),
        user=serialize_user(user),
        pending_approval=pending,
    )


# ============================================================
# ADMIN CREATES VENDOR LOGIN
# ============================================================

@router.post("/vendor-user", response_model=RegisterResponse)
async def create_vendor_user(
    request: RegisterRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Administrator-only endpoint.

    Workflow:

        1. Admin creates Vendor record.
        2. Admin creates Vendor login using this endpoint.
        3. Vendor user is linked to vendor_id.
        4. Vendor cannot create their own account.
        5. Vendor can then log in through /auth/login.
    """

    # --------------------------------------------------------
    # ONLY ADMINISTRATOR
    # --------------------------------------------------------
    ensure_permission(current_user, "users.create")

    # --------------------------------------------------------
    # Role must be vendor
    # --------------------------------------------------------
    if normalize_role(request.role) != "vendor":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be vendor for vendor user creation",
        )
    request.role = "vendor"

    # --------------------------------------------------------
    # vendor_id is mandatory
    # --------------------------------------------------------
    if not request.vendor_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="vendor_id is required",
        )

    # --------------------------------------------------------
    # Check duplicate email
    # --------------------------------------------------------
    existing_user = await get_user_by_email(db, request.email)

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # --------------------------------------------------------
    # Verify vendor exists and is active
    # --------------------------------------------------------
    vendor = await get_active_vendor(db, request.vendor_id)

    # --------------------------------------------------------
    # Prevent multiple login accounts for the same vendor
    # --------------------------------------------------------
    existing_vendor_user = await db.users.find_one(
        {
            "vendor_id": request.vendor_id,
            "role": {"$in": ["vendor", "VENDOR"]},
        }
    )

    if existing_vendor_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A login account already exists for this vendor",
        )

    # --------------------------------------------------------
    # Create vendor user
    # --------------------------------------------------------
    user = await create_user(db, request)
    await notify_admin_of_new_user(db, user, "vendor")

    return RegisterResponse(
        message=f"Vendor login created successfully for {vendor.get('vendor_name', 'vendor')}",
        user=serialize_user(user),
    )


# ============================================================
# ADMIN / MANAGER CREATES CLIENT LOGIN
# ============================================================

@router.post("/client-user", response_model=RegisterResponse)
async def create_client_user(
    request: RegisterRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Administrator / Project Manager endpoint to create Client login accounts.
    """
    ensure_permission(current_user, "users.create", "projects.create")

    # Force role to client
    request.role = "client"

    existing_user = await get_user_by_email(db, request.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    user = await create_user(db, request)
    await notify_admin_of_new_user(db, user, "Client")

    return RegisterResponse(
        message=f"Client login created successfully for {request.email}",
        user=serialize_user(user),
    )


# ============================================================
# LOGIN
# ============================================================

@router.post("/login", response_model=LoginResponse)
async def login(
    request: LoginRequest,
    db=Depends(get_database),
):
    """
    Normal login endpoint for every authorized user.

    Vendor login is allowed ONLY when:
        - user exists
        - password is correct
        - user role is vendor
        - vendor_id exists
        - linked vendor exists
        - linked vendor is active
        - user account is active
    """

    # --------------------------------------------------------
    # Check if email is in banned registry
    # --------------------------------------------------------
    banned = await db.banned_emails.find_one({"email": {"$regex": f"^{re.escape(request.email.strip())}$", "$options": "i"}})
    if banned:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been removed or blocked by an Administrator. Please contact your system administrator at admin@buildtrack.com.",
        )

    # --------------------------------------------------------
    # Find user
    # --------------------------------------------------------
    user = await get_user_by_email(db, request.email)

    # --------------------------------------------------------
    # Verify password first, so account state is only revealed
    # to someone who already holds the password.
    # --------------------------------------------------------
    password_hash = user.get("password_hash") if user else None
    pw_match = verify_password(request.password, password_hash) if password_hash else False

    if not user or not pw_match:
        await record_audit(
            db,
            "auth.login.failed",
            actor=user if user else None,
            outcome="denied",
            details={"reason": "invalid_credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # --------------------------------------------------------
    # Verify account status and role
    # --------------------------------------------------------
    user_status = normalize_role(user.get("status"))

    if str(user.get("status") or "").strip().lower() == "pending":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account is waiting for an administrator to approve it.",
        )
    if user_status != "active" and user.get("status") is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been suspended by an Administrator. Please contact your system administrator at admin@buildtrack.com.",
        )
    if normalize_canonical_role(user.get("role")) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has no valid role. Please contact your system administrator.",
        )

    # --------------------------------------------------------
    # VENDOR-SPECIFIC SECURITY CHECK
    # --------------------------------------------------------
    user_role = normalize_role(user.get("role"))

    if user_role == "vendor":
        vendor_id = user.get("vendor_id")

        # Vendor user MUST be linked to a vendor.
        if not vendor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vendor account is not linked to a vendor record",
            )

        # Vendor record MUST exist and be active.
        await get_active_vendor(db, str(vendor_id))

    # --------------------------------------------------------
    # WORKER-SPECIFIC & CONTRACTOR-SPECIFIC LINKING
    # --------------------------------------------------------
    worker_id = None
    contractor_id = None

    # Only the link a manager saved on the user counts; emails and names
    # are never used to attach someone to a worker record.
    if user.get("worker_id"):
        worker_id = str(user["worker_id"])
        if user_role == "contractor":
            contractor_id = worker_id

    # --------------------------------------------------------
    # Create JWT
    # --------------------------------------------------------
    token = create_access_token(
        subject=str(user["_id"]),
        extra_claims={
            "email": user["email"],
            "role": user["role"],
            "vendor_id": user.get("vendor_id"),
            "worker_id": worker_id,
            "contractor_id": contractor_id,
        },
    )

    return LoginResponse(
        access_token=token,
        user=serialize_user(user),
        worker_id=worker_id,
    )


# ============================================================
# SOCIAL LOGIN
# ============================================================

@router.post("/social-login", response_model=LoginResponse)
async def social_login(
    request: SocialLoginRequest,
    db=Depends(get_database),
):
    """
    Demo social login for Google/Microsoft.

    Vendor accounts are not created through social login.

    SECURITY: this endpoint never verified a Google/Microsoft ID token, so it
    issued a session for any email address it was given. It stays disabled
    until real provider token verification is implemented.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Social login is not available.",
    )

    provider = request.provider.lower().strip()

    if provider not in {"google", "microsoft"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported social login provider",
        )

    requested_role = normalize_role(request.role)

    # Vendors must be created by Admin.
    if requested_role == "vendor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Vendor social registration is not allowed. "
                "An administrator must create the vendor account."
            ),
        )

    user = await get_user_by_email(db, request.email)

    if not user:
        user = await create_social_user(
            db,
            email=request.email,
            full_name=request.full_name,
            role=request.role,
            provider=provider,
            status=request.status,
        )
        await notify_admin_of_new_user(db, user, request.role)

    # --------------------------------------------------------
    # WORKER-SPECIFIC LINKING (same as /login)
    # --------------------------------------------------------
    worker_id = None

    if user.get("worker_id"):
        worker_id = str(user["worker_id"])

    # --------------------------------------------------------
    # Create JWT
    # --------------------------------------------------------
    token = create_access_token(
        subject=str(user["_id"]),
        extra_claims={
            "email": user["email"],
            "role": user["role"],
            "vendor_id": user.get("vendor_id"),
            "worker_id": worker_id,
        },
    )

    return LoginResponse(
        access_token=token,
        user=serialize_user(user),
        worker_id=worker_id,
    )


# ============================================================
# PASSWORD RESET - REQUEST
# ============================================================

@router.post(
    "/password-reset/request",
    response_model=PasswordResetResponse,
)
async def request_password_reset(
    request: PasswordResetRequest,
    db=Depends(get_database),
):
    """
    Create a password reset token and email it to the account holder.

    The token is only included in the response when PASSWORD_RESET_RETURN_TOKEN
    is explicitly enabled outside production (local development without SMTP).
    """

    user = await get_user_by_email(db, request.email)

    generic_message = (
        "If an account exists for that email, "
        "a reset link has been generated."
    )

    if not user:
        return PasswordResetResponse(
            message=generic_message
        )

    reset_token = token_urlsafe(32)

    await set_password_reset_token(
        db,
        request.email,
        hash_password(reset_token),
        datetime.utcnow() + timedelta(minutes=30),
    )

    send_email(
        to_email=user["email"],
        subject="Reset your BuildTrack password",
        body=(
            "Use this code to reset your password within 30 minutes:\n\n"
            f"{reset_token}\n\n"
            "If you did not ask for this, ignore this email."
        ),
    )
    await record_audit(db, "auth.password_reset.requested", actor=user, resource_type="user", resource_id=str(user["_id"]))

    return_token = settings.password_reset_return_token and settings.app_env.lower() != "production"
    return PasswordResetResponse(
        message=generic_message,
        reset_token=reset_token if return_token else None,
    )


# ============================================================
# PASSWORD RESET - CONFIRM
# ============================================================

@router.post("/password-reset/confirm")
async def confirm_password_reset(
    request: PasswordResetConfirmRequest,
    db=Depends(get_database),
):
    """
    Reset password using a valid reset token.
    """

    user = await get_user_by_email(
        db,
        request.email,
    )

    if not user or not user.get("password_reset_token_hash"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    expires_at = user.get("password_reset_expires_at")

    if expires_at and expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    if not verify_password(
        request.token,
        user["password_reset_token_hash"],
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    await update_password_and_clear_reset(
        db,
        str(user["_id"]),
        hash_password(request.new_password),
    )

    return {
        "message": "Password reset successfully"
    }


# ============================================================
# CURRENT USER
# ============================================================

class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    phone: Optional[str] = None


@router.get("/me", response_model=User)
async def get_profile(
    current_user=Depends(get_current_user),
):
    """
    Return currently authenticated user's profile.
    """
    return serialize_user(current_user)


@router.put("/profile", response_model=User)
@router.put("/me", response_model=User)
async def update_profile(
    request: ProfileUpdateRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Update currently authenticated user's profile info (avatar_url, full_name, etc.).
    """
    update_data = request.model_dump(exclude_unset=True)
    if "avatar_url" in update_data and update_data["avatar_url"]:
        update_data["avatarUrl"] = update_data["avatar_url"]
    if "full_name" in update_data and update_data["full_name"]:
        update_data["name"] = update_data["full_name"]

    update_data["updated_at"] = datetime.utcnow()
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": update_data},
    )

    updated_user = await db.users.find_one({"_id": current_user["_id"]})
    return serialize_user(updated_user)


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Change password for the currently authenticated user.
    """
    if len(request.new_password.strip()) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters long",
        )

    password_hash = current_user.get("password_hash")
    if not password_hash or not verify_password(request.current_password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Incorrect current password",
        )

    await update_password_and_clear_reset(
        db,
        str(current_user["_id"]),
        hash_password(request.new_password),
    )

    return {"message": "Password changed successfully"}


@router.get("/managers", response_model=list[User])
async def list_managers_endpoint(
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Return all real registered users who have specifically signed up as Project Manager.
    """
    ensure_permission(current_user, "users.read", "projects.create")
    cursor = db.users.find({
        "role": {
            "$in": [
                "projectmanager",
                "manager",
                "Project Manager",
                "project_manager",
                "MANAGER",
                "Manager",
            ]
        }
    })
    users = await cursor.to_list(200)
    valid_users = []
    for u in users:
        serialized = serialize_user(u)
        name = serialized.full_name or ""
        email = str(serialized.email or "").strip().lower()
        if (
            name.lower() not in ["string", "none", ""]
            and "@" in email
            and not email.endswith("@example.com")
            and not email.endswith("@test.com")
            and str(u.get("status", "active")).lower() not in ["suspended", "banned"]
        ):
            valid_users.append(serialized)
    return valid_users


# ============================================================
# ADMIN USER MANAGEMENT & SECURITY
# ============================================================

class UserAdminUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    role: Optional[str] = None
    status: Optional[str] = None
    avatar_url: Optional[str] = None


@router.get("/users", response_model=list[User])
async def list_all_users_endpoint(
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Administrator endpoint to view all registered user accounts.
    """
    ensure_permission(current_user, "users.read")

    cursor = db.users.find({}).sort("created_at", -1)
    users = await cursor.to_list(500)
    return [serialize_user(u) for u in users]


@router.put("/users/{user_id}", response_model=User)
async def update_user_by_admin(
    user_id: str,
    request: UserAdminUpdate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Administrator endpoint to update any user's profile, role, or status.
    """
    ensure_permission(current_user, "users.update")

    try:
        obj_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    target = await db.users.find_one({"_id": obj_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = request.model_dump(exclude_unset=True)
    if "full_name" in update_data and update_data["full_name"]:
        update_data["name"] = update_data["full_name"]
    if "avatar_url" in update_data and update_data["avatar_url"]:
        update_data["avatarUrl"] = update_data["avatar_url"]

    old_role = normalize_canonical_role(target.get("role"))
    if "role" in update_data:
        ensure_permission(current_user, "users.roles.assign")
        new_role = normalize_canonical_role(update_data["role"])
        if new_role is None:
            raise HTTPException(status_code=400, detail="Role must be one of: " + ", ".join(CANONICAL_ROLES))
        if str(target["_id"]) == str(current_user["_id"]) and new_role != old_role:
            raise HTTPException(status_code=400, detail="You cannot change your own role")
        update_data["role"] = new_role

    update_data["updated_at"] = datetime.utcnow()
    await db.users.update_one({"_id": obj_id}, {"$set": update_data})

    if "role" in update_data and update_data["role"] != old_role:
        await record_audit(
            db,
            "user.role.changed",
            actor=current_user,
            resource_type="user",
            resource_id=user_id,
            details={"from": old_role, "to": update_data["role"]},
        )
    if "status" in update_data and update_data["status"] != target.get("status"):
        await record_audit(
            db,
            "user.status.changed",
            actor=current_user,
            resource_type="user",
            resource_id=user_id,
            details={"from": target.get("status"), "to": update_data["status"]},
        )

    updated = await db.users.find_one({"_id": obj_id})
    return serialize_user(updated)


@router.put("/profile")
async def update_my_profile(
    request: ProfileUpdateRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Update logged-in user profile (name, email, password) and notify administrators of all changes.
    """
    user_id = current_user.get("_id")
    if isinstance(user_id, str):
        try:
            user_id = ObjectId(user_id)
        except Exception:
            pass

    db_user = await db.users.find_one({"_id": user_id})
    if not db_user:
        # Fallback query by email
        user_email = (current_user.get("email") or "").strip().lower()
        db_user = await db.users.find_one({"email": {"$regex": f"^{re.escape(user_email)}$", "$options": "i"}})
        if not db_user:
            raise HTTPException(status_code=404, detail="User account not found")
        user_id = db_user["_id"]

    changes = []
    updates = {}

    old_name = db_user.get("name") or db_user.get("full_name") or ""
    old_email = (db_user.get("email") or "").strip().lower()

    # 1. Name change
    if request.name and request.name.strip() and request.name.strip() != old_name:
        new_name = request.name.strip()
        updates["name"] = new_name
        updates["full_name"] = new_name
        changes.append(f"Name changed from '{old_name}' to '{new_name}'")

    # 2. Email change
    if request.email and request.email.strip().lower() != old_email:
        new_email = request.email.strip().lower()
        # Check duplicate
        exists = await db.users.find_one({
            "email": {"$regex": f"^{re.escape(new_email)}$", "$options": "i"},
            "_id": {"$ne": user_id},
        })
        if exists:
            raise HTTPException(status_code=400, detail="Email is already in use by another account")
        banned = await db.banned_emails.find_one({"email": {"$regex": f"^{re.escape(new_email)}$", "$options": "i"}})
        if banned:
            raise HTTPException(status_code=403, detail="This email is restricted/banned")
        updates["email"] = new_email
        changes.append(f"Email changed from '{old_email}' to '{new_email}'")

    # 3. Password change
    if request.new_password:
        if len(request.new_password) < 6:
            raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
        if db_user.get("hashed_password"):
            if not request.current_password:
                raise HTTPException(status_code=400, detail="Current password is required to set a new password")
            if not verify_password(request.current_password, db_user["hashed_password"]):
                raise HTTPException(status_code=400, detail="Current password is incorrect")
        updates["hashed_password"] = hash_password(request.new_password)
        changes.append("Password was changed")

    # 4. Avatar photo change
    if request.avatar_url:
        updates["avatar_url"] = request.avatar_url
        updates["avatarUrl"] = request.avatar_url

    if not updates and not changes:
        return {
            "message": "No changes made",
            "user": serialize_user(db_user),
        }

    updates["updated_at"] = datetime.utcnow()
    await db.users.update_one({"_id": user_id}, {"$set": updates})

    updated_user = await db.users.find_one({"_id": user_id})

    # Notify Admins if any setting changed
    if changes:
        await notify_admin_of_profile_change(db, db_user, changes)

    # Generate fresh access token with updated email & name
    new_token = create_access_token(
        data={
            "sub": updated_user.get("email"),
            "role": updated_user.get("role"),
            "name": updated_user.get("name") or updated_user.get("full_name"),
            "id": str(updated_user.get("_id")),
        }
    )

    return {
        "message": "Profile settings updated successfully",
        "user": serialize_user(updated_user),
        "access_token": new_token,
        "changes": changes,
    }


@router.delete("/users/{user_id}")
async def delete_and_block_user(
    user_id: str,
    ban_email: bool = True,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Administrator endpoint to remove an unauthorized account.
    If ban_email is True, the email is recorded in banned_emails to prevent re-registration or login.
    """
    ensure_permission(current_user, "users.disable")

    try:
        obj_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    target = await db.users.find_one({"_id": obj_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    target_email = target.get("email", "").strip()

    if str(current_user.get("_id")) == str(obj_id):
        raise HTTPException(
            status_code=400,
            detail="You cannot delete your own administrator account",
        )

    if ban_email and target_email:
        await db.banned_emails.update_one(
            {"email": target_email.lower()},
            {
                "$set": {
                    "email": target_email.lower(),
                    "name": target.get("name") or target.get("full_name"),
                    "role": target.get("role"),
                    "banned_by": current_user.get("email"),
                    "banned_at": datetime.utcnow(),
                    "reason": "Removed by administrator",
                }
            },
            upsert=True,
        )

    await db.users.delete_one({"_id": obj_id})
    await record_audit(db, "user.deleted", actor=current_user, resource_type="user", resource_id=user_id, details={"email_banned": ban_email})

    return {
        "message": f"User {target_email} removed successfully and email blocked from future access.",
        "email": target_email,
        "banned": ban_email,
    }


@router.post("/users/{user_id}/status", response_model=User)
async def set_user_status(
    user_id: str,
    status_value: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """
    Administrator endpoint to suspend, ban, or reactivate a user account.
    """
    ensure_permission(current_user, "users.disable")

    try:
        obj_id = ObjectId(user_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user ID")

    target = await db.users.find_one({"_id": obj_id})
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    new_status = status_value.lower()
    await db.users.update_one(
        {"_id": obj_id},
        {"$set": {"status": new_status, "updated_at": datetime.utcnow()}},
    )

    if new_status in {"suspended", "banned"} and target.get("email"):
        await db.banned_emails.update_one(
            {"email": target["email"].lower()},
            {
                "$set": {
                    "email": target["email"].lower(),
                    "banned_by": current_user.get("email"),
                    "banned_at": datetime.utcnow(),
                    "reason": f"Status changed to {new_status}",
                }
            },
            upsert=True,
        )
    elif new_status == "active" and target.get("email"):
        await db.banned_emails.delete_one({"email": target["email"].lower()})

    await record_audit(
        db,
        "user.status.changed",
        actor=current_user,
        resource_type="user",
        resource_id=user_id,
        details={"from": target.get("status"), "to": new_status},
    )
    updated = await db.users.find_one({"_id": obj_id})
    return serialize_user(updated)