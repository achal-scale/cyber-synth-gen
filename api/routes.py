"""
API route definitions for W platform.
"""
from fastapi import APIRouter

from api import auth, messages, notifications, posts, search, users, trends, seed

router = APIRouter()

router.include_router(auth.router, prefix="/auth", tags=["auth"])
router.include_router(posts.router, prefix="/posts", tags=["posts"])
router.include_router(users.router, prefix="/users", tags=["users"])
router.include_router(users.actions_router, tags=["users"])
router.include_router(search.router, prefix="/search", tags=["search"])
router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
router.include_router(messages.router, prefix="/messages", tags=["messages"])
router.include_router(trends.router, prefix="/trends", tags=["trends"])
router.include_router(seed.router, prefix="/seed", tags=["seed"])
