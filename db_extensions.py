"""
Database - Standalone SQLAlchemy database with models and CRUD operations for W (social platform).
"""
from sqlalchemy import Column, String, DateTime, Boolean, Text, ForeignKey, Table, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from typing import List, Optional
import os
import uuid

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://testuser:testpass@localhost:5432/testdb")
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# Association tables for many-to-many relationships
followers_table = Table(
    "followers",
    Base.metadata,
    Column("follower_id", String, ForeignKey("users.id"), primary_key=True),
    Column("following_id", String, ForeignKey("users.id"), primary_key=True),
    Column("created_at", DateTime, default=datetime.utcnow),
)

likes_table = Table(
    "likes",
    Base.metadata,
    Column("user_id", String, ForeignKey("users.id"), primary_key=True),
    Column("post_id", String, ForeignKey("posts.id"), primary_key=True),
    Column("created_at", DateTime, default=datetime.utcnow),
)

blocks_table = Table(
    "blocks",
    Base.metadata,
    Column("blocker_id", String, ForeignKey("users.id"), primary_key=True),
    Column("blocked_id", String, ForeignKey("users.id"), primary_key=True),
    Column("created_at", DateTime, default=datetime.utcnow),
)

mutes_table = Table(
    "mutes",
    Base.metadata,
    Column("muter_id", String, ForeignKey("users.id"), primary_key=True),
    Column("muted_id", String, ForeignKey("users.id"), primary_key=True),
    Column("created_at", DateTime, default=datetime.utcnow),
)


class User(Base):
    """User model for W platform."""

    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=False)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String, nullable=True)
    cover_url = Column(String, nullable=True)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    posts = relationship("Post", back_populates="author", foreign_keys="Post.author_id")
    liked_posts = relationship("Post", secondary=likes_table, back_populates="liked_by")

    # Followers/Following
    followers = relationship(
        "User",
        secondary=followers_table,
        primaryjoin=id == followers_table.c.following_id,
        secondaryjoin=id == followers_table.c.follower_id,
        backref="following",
    )

    blocked_users = relationship(
        "User",
        secondary=blocks_table,
        primaryjoin=id == blocks_table.c.blocker_id,
        secondaryjoin=id == blocks_table.c.blocked_id,
        backref="blocked_by",
    )

    muted_users = relationship(
        "User",
        secondary=mutes_table,
        primaryjoin=id == mutes_table.c.muter_id,
        secondaryjoin=id == mutes_table.c.muted_id,
        backref="muted_by",
    )


class Post(Base):
    """Post model for W platform."""

    __tablename__ = "posts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content = Column(Text, nullable=False)
    author_id = Column(String, ForeignKey("users.id"), nullable=False)
    reply_to_id = Column(String, ForeignKey("posts.id"), nullable=True)
    repost_of_id = Column(String, ForeignKey("posts.id"), nullable=True)
    media_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    author = relationship("User", back_populates="posts", foreign_keys=[author_id])
    liked_by = relationship("User", secondary=likes_table, back_populates="liked_posts")
    replies = relationship("Post", backref="reply_to", remote_side=[id], foreign_keys=[reply_to_id])
    reposts = relationship("Post", backref="repost_of", remote_side=[id], foreign_keys=[repost_of_id])


# Create all tables
Base.metadata.create_all(bind=engine)


class Database:
    """Standalone database with CRUD operations for W platform."""

    def __init__(self):
        self.session = SessionLocal()

    def close(self) -> None:
        """Close the database session."""
        self.session.close()

    # User operations
    def create_user(
        self,
        username: str,
        display_name: str,
        bio: Optional[str] = None,
        avatar_url: Optional[str] = None,
        cover_url: Optional[str] = None,
        verified: bool = False,
    ) -> User:
        """Create a new user."""
        user = User(
            username=username,
            display_name=display_name,
            bio=bio,
            avatar_url=avatar_url,
            cover_url=cover_url,
            verified=verified,
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        return self.session.query(User).filter(User.id == user_id).first()

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get a user by username."""
        return self.session.query(User).filter(User.username == username).first()

    def list_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        """List all users with pagination."""
        return self.session.query(User).offset(skip).limit(limit).all()

    def update_user(self, user_id: str, **kwargs) -> Optional[User]:
        """Update a user's information."""
        user = self.get_user(user_id)
        if not user:
            return None

        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)

        user.updated_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(user)
        return user

    def delete_user(self, user_id: str) -> bool:
        """Delete a user."""
        user = self.get_user(user_id)
        if not user:
            return False
        self.session.delete(user)
        self.session.commit()
        return True

    # Post operations
    def create_post(
        self,
        author_id: str,
        content: str,
        reply_to_id: Optional[str] = None,
        repost_of_id: Optional[str] = None,
        media_url: Optional[str] = None,
    ) -> Post:
        """Create a new post."""
        post = Post(
            author_id=author_id,
            content=content,
            reply_to_id=reply_to_id,
            repost_of_id=repost_of_id,
            media_url=media_url,
        )
        self.session.add(post)
        self.session.commit()
        self.session.refresh(post)
        return post

    def get_post(self, post_id: str) -> Optional[Post]:
        """Get a post by ID."""
        return self.session.query(Post).filter(Post.id == post_id).first()

    def list_posts(self, skip: int = 0, limit: int = 100) -> List[Post]:
        """List all posts with pagination, ordered by creation date (newest first)."""
        return self.session.query(Post).order_by(Post.created_at.desc()).offset(skip).limit(limit).all()

    def get_user_posts(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Post]:
        """Get all posts by a specific user."""
        return (
            self.session.query(Post)
            .filter(Post.author_id == user_id)
            .order_by(Post.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_user_timeline(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Post]:
        """Get timeline for a user (posts from people they follow + their own)."""
        user = self.get_user(user_id)
        if not user:
            return []

        following_ids = [u.id for u in user.following] + [user_id]
        return (
            self.session.query(Post)
            .filter(Post.author_id.in_(following_ids))
            .order_by(Post.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_post_replies(self, post_id: str, skip: int = 0, limit: int = 100) -> List[Post]:
        """Get all replies to a post."""
        return (
            self.session.query(Post)
            .filter(Post.reply_to_id == post_id)
            .order_by(Post.created_at.asc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def delete_post(self, post_id: str) -> bool:
        """Delete a post."""
        post = self.get_post(post_id)
        if not post:
            return False
        self.session.delete(post)
        self.session.commit()
        return True

    # Like operations
    def like_post(self, user_id: str, post_id: str) -> bool:
        """Like a post."""
        user = self.get_user(user_id)
        post = self.get_post(post_id)

        if not user or not post:
            return False

        if post not in user.liked_posts:
            user.liked_posts.append(post)
            self.session.commit()

        return True

    def unlike_post(self, user_id: str, post_id: str) -> bool:
        """Unlike a post."""
        user = self.get_user(user_id)
        post = self.get_post(post_id)

        if not user or not post:
            return False

        if post in user.liked_posts:
            user.liked_posts.remove(post)
            self.session.commit()

        return True

    def get_post_likes_count(self, post_id: str) -> int:
        """Get the number of likes for a post."""
        post = self.get_post(post_id)
        if not post:
            return 0
        return len(post.liked_by)

    def get_user_liked_posts(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Post]:
        """Get all posts liked by a user."""
        user = self.get_user(user_id)
        if not user:
            return []
        return user.liked_posts[skip : skip + limit]

    def is_post_liked_by_user(self, user_id: str, post_id: str) -> bool:
        """Check if a user has liked a post."""
        user = self.get_user(user_id)
        post = self.get_post(post_id)

        if not user or not post:
            return False

        return post in user.liked_posts

    # Follow operations
    def follow_user(self, follower_id: str, following_id: str) -> bool:
        """Follow a user."""
        if follower_id == following_id:
            return False  # Can't follow yourself

        follower = self.get_user(follower_id)
        following = self.get_user(following_id)

        if not follower or not following:
            return False

        if following not in follower.following:
            follower.following.append(following)
            self.session.commit()

        return True

    def unfollow_user(self, follower_id: str, following_id: str) -> bool:
        """Unfollow a user."""
        follower = self.get_user(follower_id)
        following = self.get_user(following_id)

        if not follower or not following:
            return False

        if following in follower.following:
            follower.following.remove(following)
            self.session.commit()

        return True

    def get_followers(self, user_id: str, skip: int = 0, limit: int = 100) -> List[User]:
        """Get all followers of a user."""
        user = self.get_user(user_id)
        if not user:
            return []
        return user.followers[skip : skip + limit]

    def get_following(self, user_id: str, skip: int = 0, limit: int = 100) -> List[User]:
        """Get all users that a user is following."""
        user = self.get_user(user_id)
        if not user:
            return []
        return user.following[skip : skip + limit]

    def get_followers_count(self, user_id: str) -> int:
        """Get the number of followers for a user."""
        user = self.get_user(user_id)
        if not user:
            return 0
        return len(user.followers)

    def get_following_count(self, user_id: str) -> int:
        """Get the number of users that a user is following."""
        user = self.get_user(user_id)
        if not user:
            return 0
        return len(user.following)

    def is_following(self, follower_id: str, following_id: str) -> bool:
        """Check if a user is following another user."""
        follower = self.get_user(follower_id)
        following = self.get_user(following_id)

        if not follower or not following:
            return False

        return following in follower.following

    # Block/mute operations
    def block_user(self, blocker_id: str, blocked_id: str) -> bool:
        """Block a user."""
        blocker = self.get_user(blocker_id)
        blocked = self.get_user(blocked_id)
        if not blocker or not blocked:
            return False
        if blocked not in blocker.blocked_users:
            blocker.blocked_users.append(blocked)
            self.session.commit()
        return True

    def unblock_user(self, blocker_id: str, blocked_id: str) -> bool:
        """Unblock a user."""
        blocker = self.get_user(blocker_id)
        blocked = self.get_user(blocked_id)
        if not blocker or not blocked:
            return False
        if blocked in blocker.blocked_users:
            blocker.blocked_users.remove(blocked)
            self.session.commit()
        return True

    def mute_user(self, muter_id: str, muted_id: str) -> bool:
        """Mute a user."""
        muter = self.get_user(muter_id)
        muted = self.get_user(muted_id)
        if not muter or not muted:
            return False
        if muted not in muter.muted_users:
            muter.muted_users.append(muted)
            self.session.commit()
        return True

    def unmute_user(self, muter_id: str, muted_id: str) -> bool:
        """Unmute a user."""
        muter = self.get_user(muter_id)
        muted = self.get_user(muted_id)
        if not muter or not muted:
            return False
        if muted in muter.muted_users:
            muter.muted_users.remove(muted)
            self.session.commit()
        return True

    def is_blocked(self, blocker_id: str, blocked_id: str) -> bool:
        """Check if blocker has blocked blocked user."""
        blocker = self.get_user(blocker_id)
        blocked = self.get_user(blocked_id)
        if not blocker or not blocked:
            return False
        return blocked in blocker.blocked_users

    def is_muted(self, muter_id: str, muted_id: str) -> bool:
        """Check if muter has muted muted user."""
        muter = self.get_user(muter_id)
        muted = self.get_user(muted_id)
        if not muter or not muted:
            return False
        return muted in muter.muted_users

    # Statistics
    def get_user_stats(self, user_id: str) -> dict:
        """Get statistics for a user."""
        user = self.get_user(user_id)
        if not user:
            return {}

        return {
            "posts_count": len(user.posts),
            "followers_count": self.get_followers_count(user_id),
            "following_count": self.get_following_count(user_id),
            "likes_count": len(user.liked_posts),
        }
