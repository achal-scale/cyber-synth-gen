"""
api/messages.py - Direct messaging routes
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import Block, DirectMessage, Notification, User
from schemas import (
    ConversationCreate,
    ConversationResponse,
    ConversationsResponse,
    CountResponse,
    MessageCreate,
    MessageEnvelope,
    MessageResponse,
    ThreadResponse,
)

router = APIRouter()


def _is_blocked(db: Session, requester_id: str, target_id: str) -> bool:
    return db.query(Block).filter(
        or_(
            and_(Block.blocker_id == requester_id, Block.blocked_id == target_id),
            and_(Block.blocker_id == target_id, Block.blocked_id == requester_id),
        )
    ).first() is not None


def _get_recipient_by_username(db: Session, current_user: User, username: str) -> User:
    recipient = db.query(User).filter(User.username == username).first()
    if not recipient:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if recipient.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot message yourself")

    if _is_blocked(db, current_user.id, recipient.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is blocked")

    return recipient


def _get_or_create_dm_notification(
    db: Session,
    *,
    recipient_id: str,
    actor_id: str,
    message_id: str,
) -> None:
    existing = db.query(Notification).filter(
        Notification.recipient_id == recipient_id,
        Notification.actor_id == actor_id,
        Notification.type.in_(["message", "dm"]),
    ).first()
    if existing:
        existing.message_id = message_id
        existing.read = False
        existing.type = "message"
    else:
        db.add(Notification(
            recipient_id=recipient_id,
            actor_id=actor_id,
            type="message",
            message_id=message_id,
        ))


@router.get("/conversations", response_model=ConversationsResponse)
def get_conversations(
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    all_messages = db.query(DirectMessage).filter(
        or_(
            DirectMessage.sender_id == current_user.id,
            DirectMessage.recipient_id == current_user.id,
        )
    ).all()

    conversations_dict: dict[str, dict[str, DirectMessage]] = {}
    for msg in all_messages:
        other_user_id = msg.recipient_id if msg.sender_id == current_user.id else msg.sender_id
        if other_user_id not in conversations_dict or msg.created_at > conversations_dict[other_user_id][
            "last_message"
        ].created_at:
            conversations_dict[other_user_id] = {
                "other_user_id": other_user_id,
                "last_message": msg,
            }

    sorted_conversations = sorted(
        conversations_dict.values(),
        key=lambda x: x["last_message"].created_at,
        reverse=True,
    )[:limit]

    conversation_responses = []
    for conv in sorted_conversations:
        other_user = db.query(User).filter(User.id == conv["other_user_id"]).first()
        if not other_user:
            continue

        unread_count = db.query(func.count(DirectMessage.id)).filter(
            DirectMessage.sender_id == other_user.id,
            DirectMessage.recipient_id == current_user.id,
            DirectMessage.read.is_(False),
        ).scalar() or 0

        conversation_responses.append(
            ConversationResponse(
                other_user=other_user,
                last_message=MessageResponse.model_validate(conv["last_message"]),
                unread_count=unread_count,
            )
        )

    return ConversationsResponse(conversations=conversation_responses)


@router.post("/conversations", response_model=ThreadResponse, status_code=status.HTTP_201_CREATED)
def create_or_get_conversation(
    conversation_data: ConversationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    recipient = _get_recipient_by_username(db, current_user, conversation_data.username)

    messages = db.query(DirectMessage).filter(
        or_(
            and_(DirectMessage.sender_id == current_user.id, DirectMessage.recipient_id == recipient.id),
            and_(DirectMessage.sender_id == recipient.id, DirectMessage.recipient_id == current_user.id),
        )
    ).order_by(desc(DirectMessage.created_at)).limit(50).all()

    messages.reverse()
    return ThreadResponse(
        messages=[MessageResponse.model_validate(message) for message in messages],
        other_user=recipient,
    )


@router.get("/conversations/{username}", response_model=ThreadResponse)
def get_message_thread(
    username: str,
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[str] = Query(None, alias="before_id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    other_user = db.query(User).filter(User.username == username).first()
    if not other_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    query = db.query(DirectMessage).filter(
        or_(
            and_(DirectMessage.sender_id == current_user.id, DirectMessage.recipient_id == other_user.id),
            and_(DirectMessage.sender_id == other_user.id, DirectMessage.recipient_id == current_user.id),
        )
    )

    if before_id:
        before_message = db.query(DirectMessage).filter(DirectMessage.id == before_id).first()
        if before_message:
            query = query.filter(DirectMessage.created_at < before_message.created_at)

    messages = query.order_by(desc(DirectMessage.created_at)).limit(limit).all()

    db.query(DirectMessage).filter(
        DirectMessage.sender_id == other_user.id,
        DirectMessage.recipient_id == current_user.id,
        DirectMessage.read.is_(False),
    ).update({DirectMessage.read: True}, synchronize_session=False)
    db.commit()

    messages.reverse()
    message_responses = [MessageResponse.model_validate(msg) for msg in messages]

    return ThreadResponse(messages=message_responses, other_user=other_user)


@router.get("/{username}", response_model=ThreadResponse)
def get_message_thread_alias(
    username: str,
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[str] = Query(None, alias="before_id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_message_thread(username, limit, before_id, db, current_user)


@router.post("/conversations/{username}", response_model=MessageEnvelope, status_code=status.HTTP_201_CREATED)
def send_message(
    username: str,
    message_data: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    recipient = _get_recipient_by_username(db, current_user, username)

    new_message = DirectMessage(
        sender_id=current_user.id,
        recipient_id=recipient.id,
        content=message_data.content,
    )

    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    _get_or_create_dm_notification(
        db,
        recipient_id=recipient.id,
        actor_id=current_user.id,
        message_id=new_message.id,
    )
    db.commit()

    return MessageEnvelope(message=MessageResponse.model_validate(new_message))


@router.post("/{username}", response_model=MessageEnvelope, status_code=status.HTTP_201_CREATED)
def send_message_by_username(
    username: str,
    message_data: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return send_message(username, message_data, db, current_user)


@router.get("/unread-count", response_model=CountResponse)
def get_unread_message_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = db.query(func.count(DirectMessage.id)).filter(
        DirectMessage.recipient_id == current_user.id,
        DirectMessage.read.is_(False),
    ).scalar() or 0

    return CountResponse(count=count)
