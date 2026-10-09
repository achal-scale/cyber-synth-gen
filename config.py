"""
config.py - Application configuration for W social platform.
"""
import os
import secrets
from pydantic_settings import BaseSettings

# The JWT secret is read from the environment; if it is unset, fall back to a
# random per-process value rather than a well-known constant.
_DEFAULT_SECRET_KEY = os.getenv("SECRET_KEY") or secrets.token_hex(32)


class Settings(BaseSettings):
    APP_NAME: str = "W"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:////data/w.db")
    UPLOAD_ROOT: str = os.getenv("UPLOAD_ROOT", "/data/uploads")
    SECRET_KEY: str = _DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    SECURE_COOKIES: bool = os.getenv("SECURE_COOKIES", "false").lower() == "true"
    RATE_LIMIT_POSTS: int = 300
    RATE_LIMIT_WINDOW_HOURS: int = 3

    class Config:
        env_file = ".env"


settings = Settings()
