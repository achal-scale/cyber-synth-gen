"""
api/trends.py - Trends read endpoints
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from database import get_db
from models import Post, Trend
from schemas import TrendResponse, TrendsResponse

router = APIRouter()


def _trend_tag_normalized(name: str) -> str:
    """Extract normalized tag from trend name (e.g. '#AI' -> 'ai')."""
    t = (name or "").strip()
    if t.startswith("#"):
        t = t[1:]
    return t.strip().lower()


@router.get("", response_model=TrendsResponse)
def list_trends(db: Session = Depends(get_db)) -> TrendsResponse:
    try:
        trends = (
            db.query(Trend)
            .order_by(desc(Trend.created_at))
            .all()
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server error") from exc

    out = []
    for trend in trends:
        tag = _trend_tag_normalized(trend.name)
        if not tag:
            continue
        actual_count = (
            db.query(func.count(Post.id))
            .filter(Post.content.ilike(f"%#{tag}%"))
            .scalar()
            or 0
        )
        out.append(
            TrendResponse(id=trend.id, name=trend.name, post_count=actual_count)
        )

    out.sort(key=lambda t: (-t.post_count, t.name))
    return TrendsResponse(trends=out)
