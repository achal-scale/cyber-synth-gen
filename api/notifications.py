"""
api/notifications.py - Notification management routes
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import Notification, User
from schemas import (
    CountResponse,
    MarkAllReadResponse,
    NotificationsResponse,
    NotificationResponse,
    SuccessResponse,
)
from api.posts import _build_post_response, _prefetch_parents

router = APIRouter()


def _conversation_user(notification: Notification) -> Optional[User]:
    if notification.type != "dm":
        return None
    if notification.actor:
        return notification.actor
    return None


@router.get("", response_model=NotificationsResponse)
def get_notifications(
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[str] = Query(None, alias="before_id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Notification).filter(Notification.recipient_id == current_user.id)

    if before_id:
        before_notification = db.query(Notification).filter(Notification.id == before_id).first()
        if before_notification:
            query = query.filter(Notification.created_at < before_notification.created_at)

    notifications = query.order_by(desc(Notification.created_at)).limit(limit + 1).all()
    has_more = len(notifications) > limit
    if has_more:
        notifications = notifications[:limit]

    notif_posts = [n.post for n in notifications if n.post]
    pmap = _prefetch_parents(notif_posts, db)

    notification_responses = []
    for notif in notifications:
        post_response = None
        if notif.post:
            post_response = _build_post_response(notif.post, current_user, db, parents_map=pmap)
        conversation_user = _conversation_user(notif)
        notification_responses.append(
            NotificationResponse(
                id=notif.id,
                type=notif.type,
                actor=notif.actor,
                post=post_response,
                message_id=notif.message_id,
                conversation_user=conversation_user,
                created_at=notif.created_at,
                read=notif.read,
            )
        )

    return NotificationsResponse(notifications=notification_responses, has_more=has_more)


@router.get("/unread-count", response_model=CountResponse)
def get_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = db.query(Notification).filter(
        Notification.recipient_id == current_user.id,
        Notification.read.is_(False),
    ).count()

    return CountResponse(count=count)


@router.post("/{notification_id}/read", response_model=SuccessResponse)
def mark_notification_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = db.query(Notification).filter(Notification.id == notification_id).first()

    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    if notification.recipient_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your notification")

    notification.read = True
    db.commit()

    return SuccessResponse(success=True)


@router.post("/mark-all-read", response_model=MarkAllReadResponse)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Notification).filter(
        Notification.recipient_id == current_user.id,
        Notification.read.is_(False),
    )
    marked_count = query.count()
    query.update({Notification.read: True}, synchronize_session=False)
    db.commit()

    return MarkAllReadResponse(success=True, marked_count=marked_count)
