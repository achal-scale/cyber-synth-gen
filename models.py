"""
models.py - SQLAlchemy database models for W application
"""
from sqlalchemy import Column, String, DateTime, Boolean, Text, ForeignKey, UniqueConstraint, Integer, LargeBinary
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import uuid

Base = declarative_base()


def generate_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    username = Column(String(255), unique=True, nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    email = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    bio = Column(String(255), nullable=True)
    avatar_url = Column(String, nullable=True)
    cover_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    verified = Column(Boolean, default=False)

    # Relationships
    posts = relationship("Post", back_populates="author", foreign_keys="Post.author_id")
    likes = relationship("Like", back_populates="user", cascade="all, delete-orphan")
    reposts = relationship("Repost", back_populates="user", cascade="all, delete-orphan")
    notifications_received = relationship(
        "Notification",
        back_populates="recipient",
        foreign_keys="Notification.recipient_id",
    )
    notifications_sent = relationship(
        "Notification",
        back_populates="actor",
        foreign_keys="Notification.actor_id",
    )
    sent_messages = relationship(
        "DirectMessage",
        back_populates="sender",
        foreign_keys="DirectMessage.sender_id",
    )
    received_messages = relationship(
        "DirectMessage",
        back_populates="recipient",
        foreign_keys="DirectMessage.recipient_id",
    )


class Post(Base):
    __tablename__ = "posts"

    id = Column(String, primary_key=True, default=generate_uuid)
    author_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    image_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    parent_post_id = Column(String, ForeignKey("posts.id", ondelete="SET NULL"), nullable=True, index=True)
    is_repost = Column(Boolean, default=False)
    original_post_id = Column(String, ForeignKey("posts.id", ondelete="CASCADE"), nullable=True)

    # Relationships
    author = relationship("User", back_populates="posts", foreign_keys=[author_id])
    likes = relationship("Like", back_populates="post", cascade="all, delete-orphan")
    reposts = relationship("Repost", back_populates="post", cascade="all, delete-orphan")
    replies = relationship(
        "Post",
        backref="parent_post",
        remote_side=[id],
        foreign_keys=[parent_post_id],
    )
    original_post = relationship("Post", remote_side=[id], foreign_keys=[original_post_id])


class Like(Base):
    __tablename__ = "likes"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    post_id = Column(String, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "post_id", name="unique_user_post_like"),)

    # Relationships
    user = relationship("User", back_populates="likes")
    post = relationship("Post", back_populates="likes")


class Repost(Base):
    __tablename__ = "reposts"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    post_id = Column(String, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("user_id", "post_id", name="unique_user_post_repost"),)

    # Relationships
    user = relationship("User", back_populates="reposts")
    post = relationship("Post", back_populates="reposts")


class Follow(Base):
    __tablename__ = "follows"

    id = Column(String, primary_key=True, default=generate_uuid)
    follower_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    following_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("follower_id", "following_id", name="unique_follower_following"),)


class DirectMessage(Base):
    __tablename__ = "direct_messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    sender_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    recipient_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(Text, nullable=False)  # 10,000 char limit enforced in validation
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    read = Column(Boolean, default=False)

    # Relationships
    sender = relationship("User", back_populates="sent_messages", foreign_keys=[sender_id])
    recipient = relationship("User", back_populates="received_messages", foreign_keys=[recipient_id])


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=generate_uuid)
    recipient_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(255), nullable=False)  # 'like', 'repost', 'reply', 'follow', 'mention', 'dm'
    post_id = Column(String, ForeignKey("posts.id", ondelete="CASCADE"), nullable=True)
    message_id = Column(String, ForeignKey("direct_messages.id", ondelete="CASCADE"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False, index=True)
    read = Column(Boolean, default=False)

    # Relationships
    recipient = relationship("User", back_populates="notifications_received", foreign_keys=[recipient_id])
    actor = relationship("User", back_populates="notifications_sent", foreign_keys=[actor_id])
    post = relationship("Post")
    message = relationship("DirectMessage")


class Block(Base):
    __tablename__ = "blocks"

    id = Column(String, primary_key=True, default=generate_uuid)
    blocker_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    blocked_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("blocker_id", "blocked_id", name="unique_blocker_blocked"),)


class Mute(Base):
    __tablename__ = "mutes"

    id = Column(String, primary_key=True, default=generate_uuid)
    muter_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    muted_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("muter_id", "muted_id", name="unique_muter_muted"),)


class Media(Base):
    __tablename__ = "media"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    path = Column(String, nullable=False, unique=True, index=True)
    content = Column(LargeBinary, nullable=False)
    mime_type = Column(String, nullable=False)
    size_bytes = Column(Integer, nullable=False)


class Trend(Base):
    __tablename__ = "trends"

    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String(255), unique=True, nullable=False, index=True)
    post_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)
