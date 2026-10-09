"""
api/seed.py - Seed summary endpoints
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import Post, Trend, User
from schemas import SeedSummaryResponse

router = APIRouter()


@router.get("/summary", response_model=SeedSummaryResponse)
def seed_summary(db: Session = Depends(get_db)) -> SeedSummaryResponse:
    try:
        users = db.query(func.count(User.id)).scalar() or 0
        users_with_avatar = db.query(func.count(User.id)).filter(User.avatar_url.isnot(None)).scalar() or 0
        posts = db.query(func.count(Post.id)).scalar() or 0
        replies = db.query(func.count(Post.id)).filter(Post.parent_post_id.isnot(None)).scalar() or 0
        trends = db.query(func.count(Trend.id)).scalar() or 0
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error") from exc

    return SeedSummaryResponse(
        users=users,
        users_with_avatar=users_with_avatar,
        posts=posts,
        replies=replies,
        trends=trends,
    )
