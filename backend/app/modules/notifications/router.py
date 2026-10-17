from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.permissions import ensure_permission
from app.core.security import get_current_user
from app.db.mongodb import get_database
from app.modules.notifications.db import (
    check_and_create_deadline_notifications,
    create_notification,
    delete_notification,
    delete_old_notifications,
    get_notification,
    get_unread_notification_count,
    get_unread_notifications,
    get_user_notifications,
    mark_all_as_read,
    mark_as_read,
)
from app.modules.notifications.models import Notification, NotificationCreate

router = APIRouter()


def serialize_doc(doc: dict) -> dict:
    """Convert MongoDB doc to dict matching Pydantic Notification model requirements."""
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
        doc["id"] = doc["_id"]

    user_id = doc.get("user_id") or doc.get("receiver_id") or ""
    doc["user_id"] = str(user_id)
    doc["receiver_id"] = str(user_id)

    doc.setdefault("title", "Notification")
    doc.setdefault("message", "")
    doc.setdefault("type", doc.get("notification_type", "info"))
    doc.setdefault("category", "system")
    doc.setdefault("is_read", False)

    created = doc.get("created_at") or datetime.now(timezone.utc)
    if isinstance(created, datetime) and created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    doc["created_at"] = created

    updated = doc.get("updated_at") or created
    if isinstance(updated, datetime) and updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    doc["updated_at"] = updated

    return doc


@router.post("/", response_model=Notification)
async def create_notification_endpoint(
    notification: NotificationCreate,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Create new notification (Admin or system)"""
    ensure_permission(current_user, "notifications.send.assigned")

    notification_data = notification.model_dump(exclude_none=True)
    if not notification_data.get("user_id") and not notification_data.get("receiver_id"):
        notification_data["user_id"] = str(current_user["_id"])

    result = await create_notification(db, notification_data)
    return Notification(**serialize_doc(result))


@router.get("/unread-count")
async def get_unread_count_endpoint(
    category: Optional[str] = Query(None, description="Optional category filter"),
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get unread notification count for current user"""
    user_id = str(current_user["_id"])
    count = await get_unread_notification_count(db, user_id, category=category)
    return {"count": count}


@router.get("/", response_model=list[Notification])
async def list_notifications_endpoint(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
    is_read: Optional[bool] = Query(None),
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """List current user's notifications with skip, limit, category, and is_read filtering."""
    user_id = str(current_user["_id"])
    notifications = await get_user_notifications(
        db, user_id, skip=skip, limit=limit, category=category, is_read=is_read
    )
    return [Notification(**serialize_doc(n)) for n in notifications]


@router.get("/user/all", response_model=list[Notification])
async def get_user_notifications_endpoint(
    limit: int = 20,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get current user's notifications (compatibility endpoint)"""
    user_id = str(current_user["_id"])
    notifications = await get_user_notifications(db, user_id, limit=limit)
    return [Notification(**serialize_doc(n)) for n in notifications]


@router.get("/user/unread", response_model=list[Notification])
async def get_unread_notifications_endpoint(
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get unread notifications for current user (compatibility endpoint)"""
    user_id = str(current_user["_id"])
    notifications = await get_unread_notifications(db, user_id)
    return [Notification(**serialize_doc(n)) for n in notifications]


@router.get("/{notification_id}", response_model=Notification)
async def get_notification_endpoint(
    notification_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Get notification by ID"""
    notification = await get_notification(db, notification_id)
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    owner_id = str(notification.get("user_id") or notification.get("receiver_id") or "")
    if owner_id != str(current_user["_id"]) and current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access other user's notification",
        )

    return Notification(**serialize_doc(notification))


@router.patch("/{notification_id}/read", response_model=Notification)
@router.put("/{notification_id}/read", response_model=Notification)
@router.post("/{notification_id}/read", response_model=Notification)
async def mark_notification_as_read_endpoint(
    notification_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Mark notification as read"""
    notification = await get_notification(db, notification_id)
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    owner_id = str(notification.get("user_id") or notification.get("receiver_id") or "")
    if owner_id != str(current_user["_id"]) and current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot mark other user's notifications",
        )

    result = await mark_as_read(db, notification_id)
    return Notification(**serialize_doc(result))


@router.patch("/read-all")
@router.post("/user/read-all")
async def mark_all_notifications_as_read_endpoint(
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Mark all user's notifications as read"""
    user_id = str(current_user["_id"])
    modified_count = await mark_all_as_read(db, user_id)
    return {"message": f"Marked {modified_count} notifications as read", "count": modified_count}


@router.delete("/{notification_id}")
async def delete_notification_endpoint(
    notification_id: str,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Delete notification"""
    notification = await get_notification(db, notification_id)
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    owner_id = str(notification.get("user_id") or notification.get("receiver_id") or "")
    if owner_id != str(current_user["_id"]) and current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete other user's notifications",
        )

    deleted = await delete_notification(db, notification_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return {"message": "Notification deleted successfully"}



@router.post("/check-deadlines")
async def trigger_deadline_checks(
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Trigger system scan for upcoming deadlines and generate deadline notifications"""
    ensure_permission(current_user, "notifications.send.assigned")
    count = await check_and_create_deadline_notifications(db)
    return {"message": f"Generated {count} deadline notifications", "count": count}


@router.post("/cleanup/old")
async def cleanup_old_notifications_endpoint(
    days: int = 30,
    current_user=Depends(get_current_user),
    db=Depends(get_database),
):
    """Delete notifications older than specified days"""
    ensure_permission(current_user, "records.delete")

    deleted_count = await delete_old_notifications(db, days)
    return {"message": f"Deleted {deleted_count} old notifications"}
