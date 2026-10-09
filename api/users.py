"""
api/users.py - User profile and relationship management routes
"""
from __future__ import annotations

import ipaddress
import mimetypes
import socket
import uuid
from typing import Optional
from urllib.parse import urlparse

import httpx

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user, get_current_user_optional
from models import Block, Follow, Like, Media, Mute, Notification, Post, User
from schemas import (
    BlockRequest,
    FollowActionResponse,
    MuteRequest,
    PostsListResponse,
    SuccessResponse,
    TimelineResponse,
    UserAutocompleteListResponse,
    UserAutocompleteResponse,
    UserEnvelope,
    UserListResponse,
    UserProfile,
    UserProfileEnvelope,
    UserPublicResponse,
    UserPublicWithFollowResponse,
    UserResponse,
    UserUpdate,
)
from api.posts import _build_post_response, _prefetch_parents

router = APIRouter()
actions_router = APIRouter()


def _blocked_user_ids(db: Session, current_user: User) -> set[str]:
    blocked_ids = db.query(Block.blocked_id).filter(Block.blocker_id == current_user.id).all()
    blocker_ids = db.query(Block.blocker_id).filter(Block.blocked_id == current_user.id).all()
    return {row[0] for row in blocked_ids + blocker_ids}


def _muted_user_ids(db: Session, current_user: User) -> set[str]:
    muted_ids = db.query(Mute.muted_id).filter(Mute.muter_id == current_user.id).all()
    return {row[0] for row in muted_ids}


def _validate_image_upload(upload: UploadFile) -> None:
    if not upload.content_type or not upload.content_type.startswith("image/"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file type")


def _save_upload_to_db(db: Session, upload: UploadFile, media_path: str) -> None:
    """Save an uploaded file into the media table."""
    try:
        content = upload.file.read()
        mime = upload.content_type or mimetypes.guess_type(upload.filename or "")[0] or "application/octet-stream"
        db.merge(Media(
            id=str(uuid.uuid4()),
            path=media_path,
            content=content,
            mime_type=mime,
            size_bytes=len(content),
        ))
        db.flush()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload failed") from exc


def _build_timeline(
    db: Session,
    user_id: str,
    limit: int,
    before_id: Optional[str],
    current_user: User,
    filter: str,
) -> TimelineResponse:
    blocked_ids = _blocked_user_ids(db, current_user)
    muted_ids = _muted_user_ids(db, current_user)

    if filter == "for_you":
        query = db.query(Post)
    else:
        followed_user_ids = db.query(Follow.following_id).filter(
            Follow.follower_id == user_id
        ).all()
        followed_user_ids = [row[0] for row in followed_user_ids] + [user_id]
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


@router.get("/autocomplete", response_model=UserAutocompleteListResponse)
def autocomplete_users(
    q: str = Query(..., min_length=1, max_length=15),
    limit: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    query = db.query(User).filter(
        or_(
            User.username.ilike(f"{q}%"),
            User.display_name.ilike(f"%{q}%"),
        )
    )

    if current_user:
        blocked_ids = _blocked_user_ids(db, current_user)
        if blocked_ids:
            query = query.filter(~User.id.in_(blocked_ids))

    users = query.order_by(User.username.asc()).limit(limit).all()
    responses = [
        UserAutocompleteResponse(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
        )
        for user in users
    ]

    return UserAutocompleteListResponse(users=responses)


@router.get("/suggestions", response_model=UserListResponse)
def get_suggestions(
    limit: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return users the current user does not follow, ordered by follower count (Who to follow)."""
    followed_ids = db.query(Follow.following_id).filter(
        Follow.follower_id == current_user.id
    ).all()
    followed_ids_set = {row[0] for row in followed_ids} | {current_user.id}

    blocked_ids = _blocked_user_ids(db, current_user)

    subq = (
        db.query(Follow.following_id, func.count(Follow.id).label("fc"))
        .group_by(Follow.following_id)
        .subquery()
    )
    query = (
        db.query(User)
        .outerjoin(subq, User.id == subq.c.following_id)
        .filter(~User.id.in_(followed_ids_set))
    )
    if blocked_ids:
        query = query.filter(~User.id.in_(blocked_ids))
    query = query.order_by(desc(func.coalesce(subq.c.fc, 0)), desc(User.created_at))
    total_count = query.count()
    suggested = query.limit(limit).all()

    responses = [
        UserPublicWithFollowResponse(
            **UserPublicResponse.model_validate(u).model_dump(),
            is_following=False,
        )
        for u in suggested
    ]
    return UserListResponse(users=responses, total_count=total_count)


def _host_is_blocked(host: Optional[str]) -> bool:
    """Return True if the host resolves to a non-public (private / loopback /
    link-local / reserved) address. Blocks by IP-address class, not by name."""
    if not host:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return True
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return True
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return True
    return False


def _fetch_preview(url: str) -> dict:
    """Fetch a remote image URL to cache a thumbnail preview for the client."""
    try:
        resp = httpx.get(url, timeout=5.0, follow_redirects=True)
        return {"status": resp.status_code, "content_preview": resp.text[:2000]}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


@router.patch("/me")
def update_profile(
    update_data: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    avatar_fetch = None
    cover_fetch = None

    if update_data.display_name is not None:
        current_user.display_name = update_data.display_name
    if update_data.bio is not None:
        current_user.bio = update_data.bio
    if update_data.avatar_url is not None:
        current_user.avatar_url = update_data.avatar_url
        # Generate a thumbnail preview by fetching the avatar server-side.
        avatar_fetch = _fetch_preview(update_data.avatar_url)
    if update_data.cover_url is not None:
        current_user.cover_url = update_data.cover_url
        # Cover images are fetched too, but only from public hosts.
        host = urlparse(update_data.cover_url).hostname
        if _host_is_blocked(host):
            cover_fetch = {"error": "cover image host is not allowed"}
        else:
            cover_fetch = _fetch_preview(update_data.cover_url)

    db.commit()
    db.refresh(current_user)

    return {
        "user": UserResponse.model_validate(current_user).model_dump(),
        "avatar_thumbnail": avatar_fetch,
        "cover_thumbnail": cover_fetch,
    }


@router.post("/me/avatar", response_model=UserEnvelope)
def upload_my_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return upload_avatar(current_user.id, file, db, current_user)


@router.post("/me/cover", response_model=UserEnvelope)
def upload_my_cover(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return upload_cover(current_user.id, file, db, current_user)


def _user_follow_flag(current_user: Optional[User], user_id: str, db: Session) -> bool:
    if not current_user:
        return False
    return db.query(Follow).filter(
        Follow.follower_id == current_user.id,
        Follow.following_id == user_id,
    ).first() is not None


@router.get("/{username}", response_model=UserProfileEnvelope)
def get_user_profile(
    username: str,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    followers_count = db.query(func.count(Follow.id)).filter(Follow.following_id == user.id).scalar() or 0
    following_count = db.query(func.count(Follow.id)).filter(Follow.follower_id == user.id).scalar() or 0
    posts_count = db.query(func.count(Post.id)).filter(Post.author_id == user.id).scalar() or 0

    is_following = False
    is_blocked = False
    is_muted = False

    if current_user:
        is_following = db.query(Follow).filter(
            Follow.follower_id == current_user.id,
            Follow.following_id == user.id,
        ).first() is not None
        is_blocked = db.query(Block).filter(
            Block.blocker_id == current_user.id,
            Block.blocked_id == user.id,
        ).first() is not None
        is_muted = db.query(Mute).filter(
            Mute.muter_id == current_user.id,
            Mute.muted_id == user.id,
        ).first() is not None

    profile = UserProfile(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        bio=user.bio,
        avatar_url=user.avatar_url,
        cover_url=user.cover_url,
        verified=user.verified,
        created_at=user.created_at,
        followers_count=followers_count,
        following_count=following_count,
        posts_count=posts_count,
    )

    return UserProfileEnvelope(
        user=profile,
        is_following=is_following,
        is_blocked=is_blocked,
        is_muted=is_muted,
    )


@router.get("/{username}/posts", response_model=PostsListResponse)
def get_user_posts(
    username: str,
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[str] = Query(None, alias="before_id"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    query = db.query(Post).filter(
        Post.author_id == user.id,
        Post.parent_post_id.is_(None),
    )

    if before_id:
        before_post = db.query(Post).filter(Post.id == before_id).first()
        if before_post:
            query = query.filter(Post.created_at < before_post.created_at)

    posts = query.order_by(desc(Post.created_at)).limit(limit).all()
    pmap = _prefetch_parents(posts, db)
    post_responses = [_build_post_response(post, current_user, db, parents_map=pmap) for post in posts]
    return PostsListResponse(posts=post_responses)


@router.get("/{username}/replies", response_model=PostsListResponse)
def get_user_replies(
    username: str,
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[str] = Query(None, alias="before_id"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    query = db.query(Post).filter(
        Post.author_id == user.id,
        Post.parent_post_id.isnot(None),
    )

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


@router.get("/{username}/likes", response_model=PostsListResponse)
def get_user_likes(
    username: str,
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[str] = Query(None, alias="before_id"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    query = db.query(Post).join(Like, Like.post_id == Post.id).filter(Like.user_id == user.id)

    if before_id:
        before_like = db.query(Like).filter(Like.id == before_id).first()
        if before_like:
            query = query.filter(Like.created_at < before_like.created_at)

    posts = query.order_by(desc(Like.created_at)).limit(limit).all()
    pmap = _prefetch_parents(posts, db)
    post_responses = [_build_post_response(post, current_user, db, parents_map=pmap) for post in posts]
    return PostsListResponse(posts=post_responses)


@router.get("/{username}/media", response_model=PostsListResponse)
def get_user_media(
    username: str,
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[str] = Query(None, alias="before_id"),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    query = db.query(Post).filter(
        Post.author_id == user.id,
        Post.image_url.isnot(None),
        Post.image_url != "",
    )

    if before_id:
        before_post = db.query(Post).filter(Post.id == before_id).first()
        if before_post:
            query = query.filter(Post.created_at < before_post.created_at)

    posts = query.order_by(desc(Post.created_at)).limit(limit).all()
    pmap = _prefetch_parents(posts, db)
    post_responses = [_build_post_response(post, current_user, db, parents_map=pmap) for post in posts]
    return PostsListResponse(posts=post_responses)


@router.get("/{username}/followers", response_model=UserListResponse)
def get_followers(
    username: str,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    followers_query = db.query(User).join(
        Follow, Follow.follower_id == User.id
    ).filter(Follow.following_id == user.id)

    total_count = followers_query.count()
    followers = followers_query.limit(limit).all()

    follower_responses = [
        UserPublicWithFollowResponse(
            **UserPublicResponse.model_validate(follower).model_dump(),
            is_following=_user_follow_flag(current_user, follower.id, db),
        )
        for follower in followers
    ]

    return UserListResponse(users=follower_responses, total_count=total_count)


@router.get("/{username}/following", response_model=UserListResponse)
def get_following(
    username: str,
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    following_query = db.query(User).join(
        Follow, Follow.following_id == User.id
    ).filter(Follow.follower_id == user.id)

    total_count = following_query.count()
    following = following_query.limit(limit).all()

    following_responses = [
        UserPublicWithFollowResponse(
            **UserPublicResponse.model_validate(followed).model_dump(),
            is_following=_user_follow_flag(current_user, followed.id, db),
        )
        for followed in following
    ]

    return UserListResponse(users=following_responses, total_count=total_count)


@router.post("/{username}/follow", response_model=FollowActionResponse)
def follow_user(
    username: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot follow yourself")

    existing_follow = db.query(Follow).filter(
        Follow.follower_id == current_user.id,
        Follow.following_id == user.id,
    ).first()

    if not existing_follow:
        new_follow = Follow(follower_id=current_user.id, following_id=user.id)
        db.add(new_follow)
        notification = Notification(
            recipient_id=user.id,
            actor_id=current_user.id,
            type="follow",
        )
        db.add(notification)
        db.commit()

    followers_count = db.query(func.count(Follow.id)).filter(Follow.following_id == user.id).scalar() or 0
    return FollowActionResponse(success=True, followers_count=followers_count)


@router.delete("/{username}/follow", response_model=FollowActionResponse)
def unfollow_user(
    username: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    follow = db.query(Follow).filter(
        Follow.follower_id == current_user.id,
        Follow.following_id == user.id,
    ).first()

    if follow:
        db.delete(follow)
        db.commit()

    followers_count = db.query(func.count(Follow.id)).filter(Follow.following_id == user.id).scalar() or 0
    return FollowActionResponse(success=True, followers_count=followers_count)


@router.post("/{username}/block", response_model=SuccessResponse)
def block_user(
    username: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot block yourself")

    existing_block = db.query(Block).filter(
        Block.blocker_id == current_user.id,
        Block.blocked_id == user.id,
    ).first()

    if existing_block:
        return SuccessResponse(success=True)

    db.query(Follow).filter(
        or_(
            (Follow.follower_id == current_user.id) & (Follow.following_id == user.id),
            (Follow.follower_id == user.id) & (Follow.following_id == current_user.id),
        )
    ).delete(synchronize_session=False)

    new_block = Block(blocker_id=current_user.id, blocked_id=user.id)
    db.add(new_block)
    db.commit()

    return SuccessResponse(success=True)


@router.delete("/{username}/block", response_model=SuccessResponse)
def unblock_user(
    username: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    block = db.query(Block).filter(
        Block.blocker_id == current_user.id,
        Block.blocked_id == user.id,
    ).first()

    if block:
        db.delete(block)
        db.commit()

    return SuccessResponse(success=True)


@router.post("/{username}/mute", response_model=SuccessResponse)
def mute_user(
    username: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot mute yourself")

    existing_mute = db.query(Mute).filter(
        Mute.muter_id == current_user.id,
        Mute.muted_id == user.id,
    ).first()

    if existing_mute:
        return SuccessResponse(success=True)

    new_mute = Mute(muter_id=current_user.id, muted_id=user.id)
    db.add(new_mute)
    db.commit()

    return SuccessResponse(success=True)


@router.delete("/{username}/mute", response_model=SuccessResponse)
def unmute_user(
    username: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    mute = db.query(Mute).filter(
        Mute.muter_id == current_user.id,
        Mute.muted_id == user.id,
    ).first()

    if mute:
        db.delete(mute)
        db.commit()

    return SuccessResponse(success=True)


@router.post("/{user_id}/avatar", response_model=UserEnvelope)
def upload_avatar(
    user_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot upload for another user")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    _validate_image_upload(file)
    media_path = f"uploads/{user_id}/avatar.jpg"
    _save_upload_to_db(db, file, media_path)

    user.avatar_url = f"/uploads/{user_id}/avatar.jpg"
    db.commit()
    db.refresh(user)

    return UserEnvelope(user=UserResponse.model_validate(user))


@router.post("/{user_id}/cover", response_model=UserEnvelope)
def upload_cover(
    user_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot upload for another user")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    _validate_image_upload(file)
    media_path = f"uploads/{user_id}/cover.jpg"
    _save_upload_to_db(db, file, media_path)

    user.cover_url = f"/uploads/{user_id}/cover.jpg"
    db.commit()
    db.refresh(user)

    return UserEnvelope(user=UserResponse.model_validate(user))


@router.get("/{user_id}/timeline", response_model=TimelineResponse)
def get_user_timeline(
    user_id: str,
    limit: int = Query(50, ge=1, le=100),
    before_id: Optional[str] = Query(None, alias="before_id"),
    filter: str = Query("following", pattern=r"^(for_you|following)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot access another user timeline")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return _build_timeline(db, user_id, limit, before_id, current_user, filter)


@actions_router.post("/blocks", response_model=SuccessResponse)
def block_user_by_id(
    block_data: BlockRequest,
    user_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    requester_id = user_id
    if current_user.id != requester_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot block for another user")
    if requester_id == block_data.target_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot block yourself")

    target_user = db.query(User).filter(User.id == block_data.target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing_block = db.query(Block).filter(
        Block.blocker_id == requester_id,
        Block.blocked_id == block_data.target_user_id,
    ).first()

    if not existing_block:
        db.query(Follow).filter(
            or_(
                (Follow.follower_id == requester_id) & (Follow.following_id == block_data.target_user_id),
                (Follow.follower_id == block_data.target_user_id) & (Follow.following_id == requester_id),
            )
        ).delete(synchronize_session=False)

        db.add(Block(blocker_id=requester_id, blocked_id=block_data.target_user_id))
        db.commit()

    return SuccessResponse(success=True)


@actions_router.delete("/blocks/{target_user_id}", response_model=SuccessResponse)
def unblock_user_by_path(
    target_user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    block = db.query(Block).filter(
        Block.blocker_id == current_user.id,
        Block.blocked_id == target_user_id,
    ).first()

    if block:
        db.delete(block)
        db.commit()

    return SuccessResponse(success=True)


@actions_router.delete("/blocks", response_model=SuccessResponse)
def unblock_user_by_id(
    target_user_id: str = Query(...),
    user_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot unblock for another user")

    block = db.query(Block).filter(
        Block.blocker_id == user_id,
        Block.blocked_id == target_user_id,
    ).first()

    if block:
        db.delete(block)
        db.commit()

    return SuccessResponse(success=True)


@actions_router.post("/mutes", response_model=SuccessResponse)
def mute_user_by_id(
    mute_data: MuteRequest,
    user_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    requester_id = user_id
    if current_user.id != requester_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot mute for another user")
    if requester_id == mute_data.target_user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot mute yourself")

    target_user = db.query(User).filter(User.id == mute_data.target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    existing_mute = db.query(Mute).filter(
        Mute.muter_id == requester_id,
        Mute.muted_id == mute_data.target_user_id,
    ).first()

    if not existing_mute:
        db.add(Mute(muter_id=requester_id, muted_id=mute_data.target_user_id))
        db.commit()

    return SuccessResponse(success=True)


@actions_router.delete("/mutes/{target_user_id}", response_model=SuccessResponse)
def unmute_user_by_path(
    target_user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mute = db.query(Mute).filter(
        Mute.muter_id == current_user.id,
        Mute.muted_id == target_user_id,
    ).first()

    if mute:
        db.delete(mute)
        db.commit()

    return SuccessResponse(success=True)


@actions_router.delete("/mutes", response_model=SuccessResponse)
def unmute_user_by_id(
    target_user_id: str = Query(...),
    user_id: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot unmute for another user")

    mute = db.query(Mute).filter(
        Mute.muter_id == user_id,
        Mute.muted_id == target_user_id,
    ).first()

    if mute:
        db.delete(mute)
        db.commit()

    return SuccessResponse(success=True)
