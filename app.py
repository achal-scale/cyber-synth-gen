"""
FastAPI application entry point for W platform.
"""
from contextlib import asynccontextmanager
from datetime import datetime
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from api import auth, messages, notifications, posts, search, users, trends, seed, reset
from config import settings
from database import SessionLocal, init_db
from schemas import HealthResponse
from seeds.seed_data import seed_database_from_files


class UploadsNoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/uploads"):
            response.headers["Cache-Control"] = "no-cache, max-age=0"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(settings.UPLOAD_ROOT, exist_ok=True)
    init_db()
    db = SessionLocal()
    try:
        seed_database_from_files(db)
    finally:
        db.close()
    yield


os.makedirs(settings.UPLOAD_ROOT, exist_ok=True)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    description="API for W social platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(UploadsNoCacheMiddleware)


@app.get("/api/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.utcnow())


@app.get("/")
def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
    }


def _serve_media(path: str, cache: str = "no-cache"):
    """Serve media from the database by path."""
    from models import Media
    session = SessionLocal()
    try:
        row = session.query(Media).filter(Media.path == path).first()
        if not row:
            raise HTTPException(status_code=404, detail="File not found")
        return Response(
            content=row.content,
            media_type=row.mime_type,
            headers={"Cache-Control": cache},
        )
    finally:
        session.close()


@app.get("/media/{path:path}")
def serve_media(path: str):
    """Serve media assets from the database."""
    return _serve_media(path)


@app.get("/uploads/{path:path}")
def serve_upload(path: str):
    """Serve uploaded files from the database."""
    return _serve_media(f"uploads/{path}")


@app.get("/assets/{path:path}")
def serve_asset(path: str):
    """Serve static assets from the database."""
    return _serve_media(f"assets/{path}", cache="public, max-age=86400")


app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(posts.router, prefix="/api/posts", tags=["posts"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(users.actions_router, prefix="/api", tags=["users"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(notifications.router, prefix="/api/notifications", tags=["notifications"])
app.include_router(messages.router, prefix="/api/messages", tags=["messages"])
app.include_router(trends.router, prefix="/api/trends", tags=["trends"])
app.include_router(seed.router, prefix="/api/seed", tags=["seed"])
app.include_router(reset.router, prefix="/api", tags=["reset"])
