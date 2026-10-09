"""
api/posts.py - Post management routes
"""
from __future__ import annotations

from datetime import datetime, timedelta
import os
from pathlib import Path
import re
from typing import Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from dependencies import get_current_user, get_current_user_optional
from models import Follow, Like, Notification, Post, Repost, Trend, User
from schemas import (
    HashtagPostsResponse,
    LikeActionResponse,
    ParentPostPreview,
    PostCreate,
    PostEnvelope,
    PostImageUploadResponse,
    PostResponse,
    PostsListResponse,
    RepostActionResponse,
    SuccessResponse,
    TimelineResponse,
)

router = APIRouter()

MENTION_PATTERN = re.compile(r"@([a-zA-Z0-9_]{1,15})")
HASHTAG_PATTERN = re.compile(r"#([a-zA-Z0-9_]+)")


def _prefetch_parents(posts: list[Post], db: Session) -> dict[str, Post]:
    parent_ids = {p.parent_post_id for p in posts if p.parent_post_id}
    if not parent_ids:
        return {}
    parents = db.query(Post).filter(Post.id.in_(parent_ids)).all()
    return {p.id: p for p in parents}


def _build_post_response(
    post: Post,
    current_user: Optional[User],
    db: Session,
    *,
    _depth: int = 0,
    parents_map: Optional[dict[str, Post]] = None,
) -> PostResponse:
    like_count = db.query(func.count(Like.id)).filter(Like.post_id == post.id).scalar() or 0
    repost_count = db.query(func.count(Repost.id)).filter(Repost.post_id == post.id).scalar() or 0
    reply_count = db.query(func.count(Post.id)).filter(Post.parent_post_id == post.id).scalar() or 0

    is_liked = False
    is_reposted = False
    if current_user:
        is_liked = db.query(Like).filter(
            Like.post_id == post.id,
            Like.user_id == current_user.id,
        ).first() is not None
        is_reposted = db.query(Repost).filter(
            Repost.post_id == post.id,
            Repost.user_id == current_user.id,
        ).first() is not None

    original_post_response = None
    if post.is_repost and post.original_post is not None and _depth < 1:
        original_post_response = _build_post_response(
            post.original_post,
            current_user,
            db,
            _depth=_depth + 1,
        )

    parent_preview = None
    if post.parent_post_id:
        parent = (parents_map or {}).get(post.parent_post_id)
        if parent is None and parents_map is None:
            parent = db.query(Post).filter(Post.id == post.parent_post_id).first()
        if parent:
            parent_preview = ParentPostPreview(
                id=parent.id,
                author=parent.author,
                content=parent.content,
            )

    return PostResponse(
        id=post.id,
        author=post.author,
        content=post.content,
        created_at=post.created_at,
        parent_post_id=post.parent_post_id,
        reply_count=reply_count,
        repost_count=repost_count,
        like_count=like_count,
        is_liked=is_liked,
        is_reposted=is_reposted,
        is_repost=post.is_repost,
        image_url=post.image_url,
        parent_post=parent_preview,
        original_post=original_post_response,
    )


def _blocked_user_ids(db: Session, current_user: User) -> set[str]:
    from models import Block

    blocked_ids = db.query(Block.blocked_id).filter(Block.blocker_id == current_user.id).all()
    blocker_ids = db.query(Block.blocker_id).filter(Block.blocked_id == current_user.id).all()
    return {row[0] for row in blocked_ids + blocker_ids}


def _muted_user_ids(db: Session, current_user: User) -> set[str]:
    from models import Mute

    muted_ids = db.query(Mute.muted_id).filter(Mute.muter_id == current_user.id).all()
    return {row[0] for row in muted_ids}


def _normalize_hashtag(tag: str) -> Optional[str]:
    cleaned = tag.strip()
    if cleaned.startswith("#"):
        cleaned = cleaned[1:]
    cleaned = cleaned.strip().lower()
    if not cleaned:
        return None
    if not re.fullmatch(r"[a-z0-9_]+", cleaned):
        return None
    return cleaned


def _extract_hashtags(content: str) -> set[str]:
    return {match.group(1).lower() for match in HASHTAG_PATTERN.finditer(content or "")}


def _extract_mentions(content: str) -> set[str]:
    return {match.group(1).lower() for match in MENTION_PATTERN.finditer(content or "")}


async def _save_post_image_upload(
    file: UploadFile,
    current_user: User,
) -> PostImageUploadResponse:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only image files are allowed")

    _ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
    _MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10 MB
    ext = Path(file.filename).suffix.lower() if file.filename else ".jpg"
    if ext not in _ALLOWED_EXTENSIONS:
        ext = ".jpg"
    filename = f"{uuid.uuid4()}{ext}"
    user_posts_dir = os.path.join(settings.UPLOAD_ROOT, current_user.id, "posts")
    os.makedirs(user_posts_dir, exist_ok=True)
    dest = os.path.join(user_posts_dir, filename)
    content = await file.read()
    if len(content) > _MAX_IMAGE_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Image too large (max 10 MB)")
    try:
        with open(dest, "wb") as file_obj:
            file_obj.write(content)
    except OSError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload failed") from exc

    return PostImageUploadResponse(url=f"/uploads/{current_user.id}/posts/{filename}")


@router.post("/images", response_model=PostImageUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_post_image(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> PostImageUploadResponse:
    return await _save_post_image_upload(file, current_user)


@router.post("/upload-image", response_model=PostImageUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_post_image_alias(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> PostImageUploadResponse:
    return await _save_post_image_upload(file, current_user)


@router.get("/timeline", response_model=TimelineResponse)
def get_timeline(
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[str] = Query(None, alias="before_id"),
    filter: str = Query("following", pattern=r"^(for_you|following)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    blocked_ids = _blocked_user_ids(db, current_user)
    muted_ids = _muted_user_ids(db, current_user)

    if filter == "for_you":
        query = db.query(Post)
    else:
        followed_user_ids = db.query(Follow.following_id).filter(
            Follow.follower_id == current_user.id
        ).all()
        followed_user_ids = [row[0] for row in followed_user_ids] + [current_user.id]
        query = db.query(Post).filter(Post.author_id.in_(followed_user_ids))

    if blocked_ids:
        query = query.filter(~Post.author_id.in_(blocked_ids))
    if muted_ids:
        query = query.filter(~Post.author_id.in_(muted_ids))

    if before_id:
        before_post = db.query(Post).filter(Post.id == before_id).first()
        if before_post:
            query = query.filter(Post.created_at < before_post.created_at)

    posts = query.order_by(desc(Post.created_at)).limit(limit + 1).all()
    has_more = len(posts) > limit
    if has_more:
        posts = posts[:limit]

    pmap = _prefetch_parents(posts, db)
    post_responses = [_build_post_response(post, current_user, db, parents_map=pmap) for post in posts]
    return TimelineResponse(posts=post_responses, has_more=has_more)


@router.get("/hashtags/{tag}", response_model=HashtagPostsResponse)
def get_posts_by_hashtag(
    tag: str,
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[str] = Query(None, alias="before_id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    normalized = _normalize_hashtag(tag)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tag")

    blocked_ids = _blocked_user_ids(db, current_user)
    muted_ids = _muted_user_ids(db, current_user)

    query = db.query(Post).filter(Post.content.ilike(f"%#{normalized}%"))
    if blocked_ids:
        query = query.filter(~Post.author_id.in_(blocked_ids))
    if muted_ids:
        query = query.filter(~Post.author_id.in_(muted_ids))

    if before_id:
        before_post = db.query(Post).filter(Post.id == before_id).first()
        if before_post:
            query = query.filter(Post.created_at < before_post.created_at)

    posts = query.order_by(desc(Post.created_at)).limit(limit + 1).all()
    has_more = len(posts) > limit
    if has_more:
        posts = posts[:limit]

    pmap = _prefetch_parents(posts, db)
    post_responses = [_build_post_response(post, current_user, db, parents_map=pmap) for post in posts]
    return HashtagPostsResponse(tag=normalized, posts=post_responses, has_more=has_more)


@router.get("/hashtag/{tag}", response_model=HashtagPostsResponse)
def get_posts_by_hashtag_alias(
    tag: str,
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[str] = Query(None, alias="before_id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_posts_by_hashtag(tag, limit, before_id, db, current_user)


@router.post("", response_model=PostEnvelope, status_code=status.HTTP_201_CREATED)
def create_post(
    post_data: PostCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    window_start = datetime.utcnow() - timedelta(hours=settings.RATE_LIMIT_WINDOW_HOURS)
    recent_posts_count = db.query(func.count(Post.id)).filter(
        Post.author_id == current_user.id,
        Post.created_at >= window_start,
    ).scalar() or 0

    if recent_posts_count >= settings.RATE_LIMIT_POSTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )

    parent_post = None
    parent_post_id = post_data.parent_post_id.strip() if post_data.parent_post_id else None
    if parent_post_id:
        parent_post = db.query(Post).filter(Post.id == parent_post_id).first()
        if not parent_post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parent post not found",
            )

    new_post = Post(
        author_id=current_user.id,
        content=post_data.content,
        image_url=post_data.image_url,
        parent_post_id=parent_post.id if parent_post else None,
    )

    db.add(new_post)
    db.commit()
    db.refresh(new_post)

    if parent_post and parent_post.author_id != current_user.id:
        notification = Notification(
            recipient_id=parent_post.author_id,
            actor_id=current_user.id,
            type="reply",
            post_id=new_post.id,
        )
        db.add(notification)

    hashtags = _extract_hashtags(post_data.content)
    for tag in hashtags:
        trend_name = f"#{tag}"
        trend = db.query(Trend).filter(func.lower(Trend.name) == trend_name.lower()).first()
        if trend:
            trend.post_count += 1
        else:
            db.add(Trend(name=trend_name, post_count=1))

    mention_usernames = _extract_mentions(post_data.content)
    if mention_usernames:
        normalized_to_user: dict[str, User] = {}
        mentioned_users = db.query(User).filter(
            func.lower(User.username).in_(mention_usernames)
        ).all()
        for user in mentioned_users:
            normalized_to_user[user.username.lower()] = user

        for username in mention_usernames:
            user = normalized_to_user.get(username)
            if not user or user.id == current_user.id:
                continue
            db.add(
                Notification(
                    recipient_id=user.id,
                    actor_id=current_user.id,
                    type="mention",
                    post_id=new_post.id,
                )
            )

    db.commit()

    return PostEnvelope(post=_build_post_response(new_post, current_user, db))


@router.get("/{post_id}", response_model=PostEnvelope)
def get_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    if current_user:
        blocked_ids = _blocked_user_ids(db, current_user)
        if post.author_id in blocked_ids:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Post not accessible")

    return PostEnvelope(post=_build_post_response(post, current_user, db))


@router.delete("/{post_id}", response_model=SuccessResponse)
def delete_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    if post.author_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not post owner")

    db.delete(post)
    db.commit()

    return SuccessResponse(success=True)


@router.post("/{post_id}/like", response_model=LikeActionResponse)
def like_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    existing_like = db.query(Like).filter(
        Like.post_id == post_id,
        Like.user_id == current_user.id,
    ).first()

    if not existing_like:
        new_like = Like(post_id=post_id, user_id=current_user.id)
        db.add(new_like)
        if post.author_id != current_user.id:
            notification = Notification(
                recipient_id=post.author_id,
                actor_id=current_user.id,
                type="like",
                post_id=post_id,
            )
            db.add(notification)
        db.commit()

    like_count = db.query(func.count(Like.id)).filter(Like.post_id == post_id).scalar() or 0
    return LikeActionResponse(success=True, like_count=like_count)


@router.delete("/{post_id}/like", response_model=LikeActionResponse)
def unlike_post(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    like = db.query(Like).filter(
        Like.post_id == post_id,
        Like.user_id == current_user.id,
    ).first()

    if not like:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Like not found")

    db.delete(like)
    db.commit()

    like_count = db.query(func.count(Like.id)).filter(Like.post_id == post_id).scalar() or 0
    return LikeActionResponse(success=True, like_count=like_count)


@router.post("/{post_id}/repost", response_model=RepostActionResponse)
def repost(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    existing_repost = db.query(Repost).filter(
        Repost.post_id == post_id,
        Repost.user_id == current_user.id,
    ).first()

    if not existing_repost:
        new_repost = Repost(post_id=post_id, user_id=current_user.id)
        db.add(new_repost)
        repost_post = Post(
            author_id=current_user.id,
            content=post.content,
            is_repost=True,
            original_post_id=post.id,
        )
        db.add(repost_post)
        if post.author_id != current_user.id:
            notification = Notification(
                recipient_id=post.author_id,
                actor_id=current_user.id,
                type="repost",
                post_id=post_id,
            )
            db.add(notification)
        db.commit()

    repost_count = db.query(func.count(Repost.id)).filter(Repost.post_id == post_id).scalar() or 0
    return RepostActionResponse(success=True, repost_count=repost_count)


@router.delete("/{post_id}/repost", response_model=RepostActionResponse)
def unrepost(
    post_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repost = db.query(Repost).filter(
        Repost.post_id == post_id,
        Repost.user_id == current_user.id,
    ).first()

    if not repost:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repost not found")

    db.delete(repost)
    db.commit()

    repost_count = db.query(func.count(Repost.id)).filter(Repost.post_id == post_id).scalar() or 0
    return RepostActionResponse(success=True, repost_count=repost_count)


@router.get("/{post_id}/replies", response_model=PostsListResponse)
def get_post_replies(
    post_id: str,
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[str] = Query(None, alias="before_id"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")

    query = db.query(Post).filter(Post.parent_post_id == post_id)

    if before_id:
        before_post = db.query(Post).filter(Post.id == before_id).first()
        if before_post:
            query = query.filter(Post.created_at < before_post.created_at)

    replies = query.order_by(desc(Post.created_at)).limit(limit).all()
    pmap = _prefetch_parents(replies, db)
    reply_responses = [
        _build_post_response(reply, current_user, db, parents_map=pmap) for reply in replies
    ]

    return PostsListResponse(posts=reply_responses)
