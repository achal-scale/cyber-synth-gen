"""
Seed data for the W application (file-based).
Loads JSON data and seed images from disk to initialize the database.
"""
from __future__ import annotations

import json
import mimetypes
import os
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from auth import hash_password
from models import DirectMessage, Follow, Like, Media, Notification, Post, Repost, Trend, User

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
SEED_IMAGES_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "uploads", "seed_images")
)

logger = logging.getLogger(__name__)


def _load_json(filename: str) -> List[Dict[str, Any]]:
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as file_obj:
        data = json.load(file_obj)
    if isinstance(data, list):
        return data
    return data.get("items", [])


def _parse_datetime(value: Optional[str]) -> datetime:
    if not value:
        return datetime.utcnow()
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.utcnow()


def _get_default_avatar_source() -> Optional[str]:
    if not os.path.isdir(SEED_IMAGES_DIR):
        return None
    for filename in sorted(os.listdir(SEED_IMAGES_DIR)):
        if filename.lower().startswith("avatar"):
            return filename
    return None


def _store_media_blob(db: Session, media_path: str, content: bytes, mime_type: str) -> None:
    """Insert or update a media row in the database."""
    db.merge(Media(
        id=str(uuid.uuid4()),
        path=media_path,
        content=content,
        mime_type=mime_type,
        size_bytes=len(content),
    ))


def _ensure_user_media(db: Session, user: User, avatar_source: Optional[str], cover_source: Optional[str]) -> None:
    """Read seed images from disk and store them in the media table."""
    avatar_filename = avatar_source
    if avatar_filename:
        avatar_path = os.path.join(SEED_IMAGES_DIR, avatar_filename)
        if not os.path.exists(avatar_path):
            avatar_filename = None
    if not avatar_filename:
        avatar_filename = _get_default_avatar_source()

    if avatar_filename:
        avatar_path = os.path.join(SEED_IMAGES_DIR, avatar_filename)
        if os.path.exists(avatar_path):
            with open(avatar_path, "rb") as f:
                content = f.read()
            mime = mimetypes.guess_type(avatar_path)[0] or "image/jpeg"
            media_path = f"uploads/{user.id}/avatar.jpg"
            _store_media_blob(db, media_path, content, mime)
            user.avatar_url = f"/uploads/{user.id}/avatar.jpg"
    else:
        # Store a placeholder (empty) avatar
        media_path = f"uploads/{user.id}/avatar.jpg"
        _store_media_blob(db, media_path, b"", "image/jpeg")
        user.avatar_url = f"/uploads/{user.id}/avatar.jpg"
        logger.warning("Seed avatar missing for user %s; wrote placeholder avatar.", user.id)

    if not user.avatar_url:
        media_path = f"uploads/{user.id}/avatar.jpg"
        _store_media_blob(db, media_path, b"", "image/jpeg")
        user.avatar_url = f"/uploads/{user.id}/avatar.jpg"
        logger.warning("Seed avatar missing for user %s; wrote placeholder avatar.", user.id)

    if cover_source:
        cover_path = os.path.join(SEED_IMAGES_DIR, cover_source)
        if os.path.exists(cover_path):
            with open(cover_path, "rb") as f:
                content = f.read()
            mime = mimetypes.guess_type(cover_path)[0] or "image/jpeg"
            media_path = f"uploads/{user.id}/cover.jpg"
            _store_media_blob(db, media_path, content, mime)
            user.cover_url = f"/uploads/{user.id}/cover.jpg"


def _ensure_existing_user_avatars(db: Session, users_data: List[Dict[str, Any]]) -> None:
    lookup_by_id = {entry.get("id"): entry for entry in users_data if entry.get("id")}
    lookup_by_username = {
        entry.get("username"): entry for entry in users_data if entry.get("username")
    }

    updated = False
    for user in db.query(User).all():
        if user.avatar_url and str(user.avatar_url).strip():
            continue
        entry = lookup_by_id.get(user.id) or lookup_by_username.get(user.username)
        avatar_source = entry.get("avatar_url") if entry else None
        cover_source = None
        if entry and not user.cover_url:
            cover_source = entry.get("cover_url")
        _ensure_user_media(db, user, avatar_source, cover_source)
        updated = True

    if updated:
        db.commit()


def seed_database_from_files(db: Session) -> None:
    """Seed the database from JSON files if empty."""
    users_data = _load_json("users.json")
    if db.query(User).count() > 0:
        _ensure_existing_user_avatars(db, users_data)
        return

    created_users: List[User] = []

    for entry in users_data:
        password_hash = entry.get("password_hash")
        if not password_hash:
            password_hash = hash_password(entry.get("password", "password123"))

        user_kwargs = {
            "username": entry["username"],
            "display_name": entry.get("display_name") or entry["username"],
            "email": entry["email"],
            "password_hash": password_hash,
            "bio": entry.get("bio"),
            "avatar_url": None,
            "cover_url": None,
            "verified": entry.get("verified", False),
            "created_at": _parse_datetime(entry.get("created_at")),
        }
        if entry.get("id"):
            user_kwargs["id"] = entry.get("id")

        user = User(**user_kwargs)
        db.add(user)
        created_users.append(user)

    db.commit()

    for entry, user in zip(users_data, created_users):
        _ensure_user_media(db, user, entry.get("avatar_url"), entry.get("cover_url"))

    db.commit()

    posts_data = _load_json("posts.json")
    for entry in posts_data:
        post = Post(
            id=entry.get("id"),
            author_id=entry["author_id"],
            content=entry["content"],
            created_at=_parse_datetime(entry.get("created_at")),
            parent_post_id=entry.get("parent_post_id"),
            is_repost=entry.get("is_repost", False),
            original_post_id=entry.get("original_post_id"),
            image_url=entry.get("image_url") or entry.get("media_url"),
        )
        db.add(post)
    db.commit()

    follows_data = _load_json("follows.json")
    for entry in follows_data:
        if entry["follower_id"] == entry["following_id"]:
            continue
        db.add(
            Follow(
                id=entry.get("id"),
                follower_id=entry["follower_id"],
                following_id=entry["following_id"],
                created_at=_parse_datetime(entry.get("created_at")),
            )
        )
    db.commit()

    likes_data = _load_json("likes.json")
    for entry in likes_data:
        existing = db.query(Like).filter(
            Like.user_id == entry["user_id"],
            Like.post_id == entry["post_id"],
        ).first()
        if existing:
            continue
        db.add(
            Like(
                id=entry.get("id"),
                user_id=entry["user_id"],
                post_id=entry["post_id"],
                created_at=_parse_datetime(entry.get("created_at")),
            )
        )
    db.commit()

    reposts_data = _load_json("reposts.json")
    for entry in reposts_data:
        existing = db.query(Repost).filter(
            Repost.user_id == entry["user_id"],
            Repost.post_id == entry["post_id"],
        ).first()
        if existing:
            continue
        db.add(
            Repost(
                id=entry.get("id"),
                user_id=entry["user_id"],
                post_id=entry["post_id"],
                created_at=_parse_datetime(entry.get("created_at")),
            )
        )
    db.commit()

    notifications_data = _load_json("notifications.json")
    for entry in notifications_data:
        db.add(
            Notification(
                id=entry.get("id"),
                recipient_id=entry["recipient_id"],
                actor_id=entry["actor_id"],
                type=entry["type"],
                post_id=entry.get("post_id"),
                message_id=entry.get("message_id"),
                created_at=_parse_datetime(entry.get("created_at")),
                read=entry.get("read", False),
            )
        )
    db.commit()

    messages_data = _load_json("messages.json")
    for entry in messages_data:
        db.add(
            DirectMessage(
                id=entry.get("id"),
                sender_id=entry["sender_id"],
                recipient_id=entry["recipient_id"],
                content=entry["content"],
                created_at=_parse_datetime(entry.get("created_at")),
                read=entry.get("read", False),
            )
        )
    db.commit()

    trends_data = _load_json("trends.json")
    for entry in trends_data:
        db.add(
            Trend(
                id=entry.get("id"),
                name=entry["name"],
                post_count=entry.get("post_count", 0),
                created_at=_parse_datetime(entry.get("created_at")),
                updated_at=_parse_datetime(entry.get("updated_at")),
            )
        )
    db.commit()


def seed_database(db: Session) -> None:
    """Backward-compatible entry point for seeding."""
    seed_database_from_files(db)
