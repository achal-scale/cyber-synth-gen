"""
Reset endpoint for agent-env compatibility.
Clears all data and optionally reloads from a JSON file or tar.gz archive.
"""
import io
import json
import logging
import mimetypes
import os
import tarfile
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from database import SessionLocal, engine
from models import Base, User, Post, Like, Repost, Follow, DirectMessage, Notification, Block, Mute, Trend, Media
from auth import hash_password

logger = logging.getLogger(__name__)

router = APIRouter()

TABLE_ORDER = [Notification, DirectMessage, Block, Mute, Repost, Like, Follow, Post, Trend, User, Media]

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico"}


def _extract_tar_gz(body: bytes) -> tuple[dict, dict[str, tuple[bytes, str]]]:
    """Extract data.json and image files from a tar.gz archive."""
    data_dict = {}
    images_dict = {}
    with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as tf:
        for member in tf.getmembers():
            if not member.isfile():
                continue
            name = member.name.lstrip("./")
            if name == "data.json" or name.endswith("/data.json"):
                f = tf.extractfile(member)
                if f:
                    data_dict = json.load(f)
            else:
                ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext in IMAGE_EXTENSIONS:
                    f = tf.extractfile(member)
                    if f:
                        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
                        images_dict[name] = (f.read(), mime)
    return data_dict, images_dict


def _store_media(session, images: dict[str, tuple[bytes, str]]) -> int:
    """Bulk-insert image files into the media table."""
    count = 0
    for path, (content, mime_type) in images.items():
        session.merge(Media(
            id=str(uuid.uuid4()),
            path=path,
            content=content,
            mime_type=mime_type,
            size_bytes=len(content),
        ))
        count += 1
    session.commit()
    return count


@router.post("/reset")
async def reset_database(request: Request):
    """Reset database: truncate all tables, optionally reload from JSON or tar.gz."""
    # Drop and recreate all tables (reliable across SQLite and PostgreSQL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    content_type = request.headers.get("content-type", "")
    body = await request.body()

    db = SessionLocal()
    try:
        counts = {}
        media_count = 0

        if "gzip" in content_type or "octet-stream" in content_type:
            # tar.gz archive with data.json + images
            data_dict, images_dict = _extract_tar_gz(body)
            if data_dict:
                counts = _load_from_json(db, data_dict)
            if images_dict:
                media_count = _store_media(db, images_dict)
        else:
            # JSON body (backward compatible)
            request_body = json.loads(body) if body else {}
            mock_data_path = request_body.get("mock_data_path")
            mock_data = request_body.get("data")
            if mock_data_path:
                with open(mock_data_path, "r") as f:
                    mock_data = json.load(f)
            if mock_data:
                counts = _load_from_json(db, mock_data)

        if media_count:
            counts["media"] = media_count

        return {"status": "reset", "loaded": counts}
    except Exception as e:
        db.rollback()
        logger.error(f"Reset failed: {e}", exc_info=True)
        raise
    finally:
        db.close()


@router.post("/add")
async def add_data(request: Request):
    """Add data from a file on disk. The file type is detected by extension."""
    body = await request.body()
    payload = json.loads(body) if body else {}
    file_path = payload.get("file_path")
    if not file_path:
        return JSONResponse(status_code=400, content={"error": "file_path is required"})

    if not os.path.exists(file_path):
        return JSONResponse(status_code=400, content={"error": f"File not found: {file_path}"})

    db = SessionLocal()
    try:
        counts = {}
        media_count = 0

        if file_path.endswith(".tar.gz") or file_path.endswith(".tgz"):
            with open(file_path, "rb") as f:
                data_dict, images_dict = _extract_tar_gz(f.read())
            if data_dict:
                counts = _load_from_json(db, data_dict)
            if images_dict:
                media_count = _store_media(db, images_dict)
        else:
            with open(file_path, "r") as f:
                data_dict = json.load(f)
            if data_dict:
                counts = _load_from_json(db, data_dict)

        if media_count:
            counts["media"] = media_count

        return {"status": "added", "loaded": counts}
    except Exception as e:
        db.rollback()
        logger.error(f"Add data failed: {e}", exc_info=True)
        raise
    finally:
        db.close()


def _parse_datetime(value):
    from datetime import datetime
    if not value:
        return datetime.utcnow()
    normalized = value.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return datetime.utcnow()


def _load_from_json(db, data: dict) -> dict:
    """Load all data from a single JSON dict."""
    counts = {}

    # Users
    users = data.get("users", [])
    for entry in users:
        password_hash = entry.get("password_hash")
        if not password_hash:
            password_hash = hash_password(entry.get("password", "password123"))
        user = User(
            id=entry.get("id"),
            username=entry["username"],
            display_name=entry.get("display_name") or entry["username"],
            email=entry["email"],
            password_hash=password_hash,
            bio=entry.get("bio"),
            avatar_url=entry.get("avatar_url"),
            cover_url=entry.get("cover_url"),
            verified=entry.get("verified", False),
            created_at=_parse_datetime(entry.get("created_at")),
        )
        db.add(user)
    try:
        db.commit()
        counts["users"] = len(users)
    except Exception:
        db.rollback()
        inserted = 0
        for entry in users:
            try:
                password_hash = entry.get("password_hash")
                if not password_hash:
                    password_hash = hash_password(entry.get("password", "password123"))
                db.add(User(
                    id=entry.get("id"),
                    username=entry["username"],
                    display_name=entry.get("display_name") or entry["username"],
                    email=entry["email"],
                    password_hash=password_hash,
                    bio=entry.get("bio"),
                    verified=entry.get("verified", False),
                    created_at=_parse_datetime(entry.get("created_at")),
                ))
                db.commit()
                inserted += 1
            except Exception:
                db.rollback()
        counts["users"] = inserted

    # Posts
    posts = data.get("posts", [])
    for entry in posts:
        post = Post(
            id=entry.get("id"),
            author_id=entry["author_id"],
            content=entry["content"],
            created_at=_parse_datetime(entry.get("created_at")),
            parent_post_id=entry.get("parent_post_id"),
            is_repost=entry.get("is_repost", False),
            original_post_id=entry.get("original_post_id"),
        )
        db.add(post)
    try:
        db.commit()
        counts["posts"] = len(posts)
    except Exception:
        db.rollback()
        inserted = 0
        for entry in posts:
            try:
                db.add(Post(
                    id=entry.get("id"),
                    author_id=entry["author_id"],
                    content=entry["content"],
                    created_at=_parse_datetime(entry.get("created_at")),
                    parent_post_id=entry.get("parent_post_id"),
                    is_repost=entry.get("is_repost", False),
                    original_post_id=entry.get("original_post_id"),
                ))
                db.commit()
                inserted += 1
            except Exception:
                db.rollback()
        counts["posts"] = inserted

    # Follows
    follows = data.get("follows", [])
    for entry in follows:
        if entry["follower_id"] == entry["following_id"]:
            continue
        db.add(Follow(
            id=entry.get("id"),
            follower_id=entry["follower_id"],
            following_id=entry["following_id"],
            created_at=_parse_datetime(entry.get("created_at")),
        ))
    try:
        db.commit()
        counts["follows"] = len(follows)
    except Exception:
        db.rollback()
        inserted = 0
        for entry in follows:
            if entry["follower_id"] == entry["following_id"]:
                continue
            try:
                db.add(Follow(
                    id=entry.get("id"),
                    follower_id=entry["follower_id"],
                    following_id=entry["following_id"],
                    created_at=_parse_datetime(entry.get("created_at")),
                ))
                db.commit()
                inserted += 1
            except Exception:
                db.rollback()
        counts["follows"] = inserted

    # Likes
    likes = data.get("likes", [])
    for entry in likes:
        db.add(Like(
            id=entry.get("id"),
            user_id=entry["user_id"],
            post_id=entry["post_id"],
            created_at=_parse_datetime(entry.get("created_at")),
        ))
    try:
        db.commit()
        counts["likes"] = len(likes)
    except Exception:
        db.rollback()
        inserted = 0
        for entry in likes:
            try:
                db.add(Like(
                    id=entry.get("id"),
                    user_id=entry["user_id"],
                    post_id=entry["post_id"],
                    created_at=_parse_datetime(entry.get("created_at")),
                ))
                db.commit()
                inserted += 1
            except Exception:
                db.rollback()
        counts["likes"] = inserted

    # Reposts
    reposts = data.get("reposts", [])
    for entry in reposts:
        db.add(Repost(
            id=entry.get("id"),
            user_id=entry["user_id"],
            post_id=entry["post_id"],
            created_at=_parse_datetime(entry.get("created_at")),
        ))
    try:
        db.commit()
        counts["reposts"] = len(reposts)
    except Exception:
        db.rollback()
        inserted = 0
        for entry in reposts:
            try:
                db.add(Repost(
                    id=entry.get("id"),
                    user_id=entry["user_id"],
                    post_id=entry["post_id"],
                    created_at=_parse_datetime(entry.get("created_at")),
                ))
                db.commit()
                inserted += 1
            except Exception:
                db.rollback()
        counts["reposts"] = inserted

    # Trends
    trends = data.get("trends", [])
    for entry in trends:
        db.add(Trend(
            id=entry.get("id"),
            name=entry["name"],
            post_count=entry.get("post_count", 0),
            created_at=_parse_datetime(entry.get("created_at")),
            updated_at=_parse_datetime(entry.get("updated_at")),
        ))
    try:
        db.commit()
        counts["trends"] = len(trends)
    except Exception:
        db.rollback()
        inserted = 0
        for entry in trends:
            try:
                db.add(Trend(
                    id=entry.get("id"),
                    name=entry["name"],
                    post_count=entry.get("post_count", 0),
                    created_at=_parse_datetime(entry.get("created_at")),
                    updated_at=_parse_datetime(entry.get("updated_at")),
                ))
                db.commit()
                inserted += 1
            except Exception:
                db.rollback()
        counts["trends"] = inserted

    # Notifications
    notifications = data.get("notifications", [])
    for entry in notifications:
        db.add(Notification(
            id=entry.get("id"),
            recipient_id=entry["recipient_id"],
            actor_id=entry["actor_id"],
            type=entry["type"],
            post_id=entry.get("post_id"),
            created_at=_parse_datetime(entry.get("created_at")),
            read=entry.get("read", False),
        ))
    try:
        db.commit()
        counts["notifications"] = len(notifications)
    except Exception:
        db.rollback()
        inserted = 0
        for entry in notifications:
            try:
                db.add(Notification(
                    id=entry.get("id"),
                    recipient_id=entry["recipient_id"],
                    actor_id=entry["actor_id"],
                    type=entry["type"],
                    post_id=entry.get("post_id"),
                    created_at=_parse_datetime(entry.get("created_at")),
                    read=entry.get("read", False),
                ))
                db.commit()
                inserted += 1
            except Exception:
                db.rollback()
        counts["notifications"] = inserted

    # Messages
    messages = data.get("messages", [])
    for entry in messages:
        db.add(DirectMessage(
            id=entry.get("id"),
            sender_id=entry["sender_id"],
            recipient_id=entry["recipient_id"],
            content=entry["content"],
            created_at=_parse_datetime(entry.get("created_at")),
            read=entry.get("read", False),
        ))
    try:
        db.commit()
        counts["messages"] = len(messages)
    except Exception:
        db.rollback()
        inserted = 0
        for entry in messages:
            try:
                db.add(DirectMessage(
                    id=entry.get("id"),
                    sender_id=entry["sender_id"],
                    recipient_id=entry["recipient_id"],
                    content=entry["content"],
                    created_at=_parse_datetime(entry.get("created_at")),
                    read=entry.get("read", False),
                ))
                db.commit()
                inserted += 1
            except Exception:
                db.rollback()
        counts["messages"] = inserted

    return counts
