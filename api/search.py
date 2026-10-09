"""
api/search.py - Search functionality routes
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user_optional
from models import Block, Follow, Mute, Post, Trend, User
from schemas import SearchPostsResponse, SearchUsersResponse, TrendsResponse, TrendResponse, UserPublicResponse, UserPublicWithFollowResponse
from api.posts import _build_post_response, _prefetch_parents

router = APIRouter()

HASHTAG_PATTERN = re.compile(r"#([a-zA-Z0-9_]+)")


def _blocked_user_ids(db: Session, current_user: User) -> set[str]:
    blocked_ids = db.query(Block.blocked_id).filter(Block.blocker_id == current_user.id).all()
    blocker_ids = db.query(Block.blocker_id).filter(Block.blocked_id == current_user.id).all()
    return {row[0] for row in blocked_ids + blocker_ids}


def _muted_user_ids(db: Session, current_user: User) -> set[str]:
    muted_ids = db.query(Mute.muted_id).filter(Mute.muter_id == current_user.id).all()
    return {row[0] for row in muted_ids}


@router.get("/posts", response_model=SearchPostsResponse)
def search_posts(
    q: str = Query(..., min_length=1, max_length=280),
    sort: str = Query("latest", pattern="^(latest|top)$"),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    q_normalized = q.strip()
    if not q_normalized:
        return SearchPostsResponse(posts=[])

    q_lower = q_normalized.lower()
    query = (
        db.query(Post)
        .join(User, Post.author_id == User.id)
        .filter(
            or_(
                func.lower(Post.content).contains(q_lower),
                func.lower(User.username).contains(q_lower),
                func.lower(User.display_name).contains(q_lower),
            )
        )
    )

    if current_user:
        blocked_ids = _blocked_user_ids(db, current_user)
        muted_ids = _muted_user_ids(db, current_user)
        if blocked_ids:
            query = query.filter(~Post.author_id.in_(blocked_ids))
        if muted_ids:
            query = query.filter(~Post.author_id.in_(muted_ids))

    if sort == "top":
        from models import Like
        like_count_expr = (
            db.query(func.count(Like.id))
            .filter(Like.post_id == Post.id)
            .correlate(Post)
            .scalar_subquery()
        )
        posts = query.order_by(desc(like_count_expr), desc(Post.created_at)).limit(limit).all()
    else:
        posts = query.order_by(desc(Post.created_at)).limit(limit).all()
    pmap = _prefetch_parents(posts, db)
    post_responses = [_build_post_response(post, current_user, db, parents_map=pmap) for post in posts]
    return SearchPostsResponse(posts=post_responses)


@router.get("/users", response_model=SearchUsersResponse)
def search_users(
    q: str = Query(..., min_length=1, max_length=50),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    query = db.query(User).filter(
        (User.username.ilike(f"%{q}%")) | (User.display_name.ilike(f"%{q}%"))
    )

    if current_user:
        blocked_ids = _blocked_user_ids(db, current_user)
        if blocked_ids:
            query = query.filter(~User.id.in_(blocked_ids))

    users = query.limit(limit).all()

    responses = []
    for user in users:
        is_following = False
        if current_user:
            is_following = db.query(Follow).filter(
                Follow.follower_id == current_user.id,
                Follow.following_id == user.id,
            ).first() is not None
        responses.append(
            UserPublicWithFollowResponse(
                **UserPublicResponse.model_validate(user).model_dump(),
                is_following=is_following,
            )
        )

    return SearchUsersResponse(users=responses)


@router.get("/hashtags", response_model=TrendsResponse)
def search_hashtags(
    q: str = Query(..., min_length=1, max_length=50),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    q_normalized = q.strip().lstrip("#").lower()
    if not q_normalized:
        return TrendsResponse(trends=[])

    blocked_ids: set[str] = set()
    muted_ids: set[str] = set()
    if current_user:
        blocked_ids = _blocked_user_ids(db, current_user)
        muted_ids = _muted_user_ids(db, current_user)

    trend_map: dict[str, TrendResponse] = {}

    trend_rows = db.query(Trend).filter(func.lower(Trend.name).contains(q_normalized)).all()
    for trend in trend_rows:
        tag_name = trend.name if trend.name.startswith("#") else f"#{trend.name}"
        normalized = tag_name[1:].lower()
        post_query = db.query(Post).filter(Post.content.ilike(f"%#{normalized}%"))
        if blocked_ids:
            post_query = post_query.filter(~Post.author_id.in_(blocked_ids))
        if muted_ids:
            post_query = post_query.filter(~Post.author_id.in_(muted_ids))
        post_count = post_query.count()
        trend_map[normalized] = TrendResponse(id=trend.id, name=tag_name, post_count=post_count)

    post_query = db.query(Post)
    if blocked_ids:
        post_query = post_query.filter(~Post.author_id.in_(blocked_ids))
    if muted_ids:
        post_query = post_query.filter(~Post.author_id.in_(muted_ids))

    for post in post_query.all():
        for match in HASHTAG_PATTERN.finditer(post.content or ""):
            normalized = match.group(1).lower()
            if q_normalized not in normalized:
                continue
            if normalized in trend_map:
                trend_map[normalized].post_count += 0
            else:
                count = db.query(func.count(Post.id)).filter(Post.content.ilike(f"%#{normalized}%"))
                if blocked_ids:
                    count = count.filter(~Post.author_id.in_(blocked_ids))
                if muted_ids:
                    count = count.filter(~Post.author_id.in_(muted_ids))
                trend_map[normalized] = TrendResponse(
                    id=f"hashtag-{normalized}",
                    name=f"#{normalized}",
                    post_count=count.scalar() or 0,
                )

    trends = sorted(trend_map.values(), key=lambda t: (-t.post_count, t.name.lower()))[:limit]
    return TrendsResponse(trends=trends)
