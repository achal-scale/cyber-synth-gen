"""
API package for W platform.
"""
# Import the routers that are actually used by main.py
from . import auth
from . import posts
from . import users
from . import search
from . import notifications
from . import messages
from . import trends
from . import seed

__all__ = ["auth", "posts", "users", "search", "notifications", "messages", "trends", "seed"]
