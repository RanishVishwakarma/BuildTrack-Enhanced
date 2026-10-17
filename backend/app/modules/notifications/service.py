import logging
import smtplib
from email.message import EmailMessage
from typing import Iterable

from bson import ObjectId
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.modules.auth.db import get_user_by_email, get_user_by_id
from app.modules.notifications.db import create_notification, get_users_by_role
from app.modules.notifications.models import NotificationCreate, NotificationCreateInternal, NotificationType

logger = logging.getLogger(__name__)

ROLE_ALIASES = {
    "administrator": "admin",
    "admin": "admin",
    "project manager": "manager",
    "manager": "manager",
    "site engineer": "engineer",
    "engineer": "engineer",
    "contractor": "contractor",
    "worker": "worker",
    "client": "client",
}


def normalize_role(role: str) -> str:
    return ROLE_ALIASES.get(role.strip().lower().replace("_", " "), role.strip().lower())


def notification_subject(notification_type: str) -> str:
    label = notification_type.replace("_", " ").title()
    return f"BuildTrack - {label}"


def smtp_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_from_email)


def send_notification_email(*, to_email: str, title: str, message: str, notification_type: str) -> None:
    if not smtp_configured():
        logger.info("SMTP is not configured; skipping notification email to %s", to_email)
        return

    email = EmailMessage()
    email["From"] = settings.smtp_from_email
    email["To"] = to_email
    email["Subject"] = notification_subject(notification_type)
    email.set_content(
        "\n".join(
            [
                "BuildTrack",
                "",
                title,
                "",
                message,
                "",
                f"Notification type: {notification_type}",
            ]
        )
    )

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=12) as server:
            server.starttls()
            if settings.smtp_username and settings.smtp_password:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(email)
        logger.info("Notification email sent to %s", to_email)
    except Exception:
        logger.exception("Notification email failed for %s", to_email)


async def create_notification_for_user(
    db: AsyncIOMotorDatabase,
    *,
    receiver: dict,
    title: str,
    message: str,
    notification_type: NotificationType,
    related_entity_id: str | None = None,
    related_entity_type: str | None = None,
) -> dict:
    notification_data = NotificationCreateInternal(
        receiver_id=str(receiver["_id"]),
        title=title,
        message=message,
        notification_type=notification_type,
        related_entity_id=related_entity_id,
        related_entity_type=related_entity_type,
    ).model_dump()

    result = await create_notification(db, notification_data)
    recipient_email = receiver.get("email")
    if recipient_email:
        send_notification_email(
            to_email=recipient_email,
            title=title,
            message=message,
            notification_type=notification_type,
        )
    return result


async def resolve_recipients(db: AsyncIOMotorDatabase, payload: NotificationCreate) -> list[dict]:
    if payload.recipient_type == "user":
        if not payload.receiver_email:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="receiver_email is required when recipient_type is user",
            )
        user = await get_user_by_email(db, str(payload.receiver_email))
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receiver email was not found")
        return [user]

    if payload.recipient_type == "role":
        if not payload.receiver_role:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="receiver_role is required when recipient_type is role",
            )
        users = await get_users_by_role(db, normalize_role(payload.receiver_role))
        if not users:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No users found for this role")
        return users

    if not payload.receiver_id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="receiver_id is required when recipient_type is id",
        )
    try:
        ObjectId(payload.receiver_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="receiver_id is invalid")

    user = await get_user_by_id(db, payload.receiver_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receiver id was not found")
    return [user]


async def send_notification(db: AsyncIOMotorDatabase, payload: NotificationCreate) -> list[dict]:
    recipients = await resolve_recipients(db, payload)
    created = []
    for receiver in recipients:
        created.append(
            await create_notification_for_user(
                db,
                receiver=receiver,
                title=payload.title,
                message=payload.message,
                notification_type=payload.notification_type,
                related_entity_id=payload.related_entity_id,
                related_entity_type=payload.related_entity_type,
            )
        )
    return created


async def notify_role(
    db: AsyncIOMotorDatabase,
    *,
    role: str,
    title: str,
    message: str,
    notification_type: NotificationType,
    related_entity_id: str | None = None,
    related_entity_type: str | None = None,
) -> list[dict]:
    payload = NotificationCreate(
        recipient_type="role",
        receiver_role=role,
        title=title,
        message=message,
        type=notification_type,
        related_entity_id=related_entity_id,
        related_entity_type=related_entity_type,
    )
    try:
        return await send_notification(db, payload)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_404_NOT_FOUND:
            logger.info("No notification recipients found for role %s", role)
            return []
        raise


async def notify_roles(
    db: AsyncIOMotorDatabase,
    *,
    roles: Iterable[str],
    title: str,
    message: str,
    notification_type: NotificationType,
    related_entity_id: str | None = None,
    related_entity_type: str | None = None,
) -> list[dict]:
    created: list[dict] = []
    for role in roles:
        created.extend(
            await notify_role(
                db,
                role=role,
                title=title,
                message=message,
                notification_type=notification_type,
                related_entity_id=related_entity_id,
                related_entity_type=related_entity_type,
            )
        )
    return created
