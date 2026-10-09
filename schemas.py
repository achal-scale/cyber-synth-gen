"""
schemas.py - Pydantic models for request/response validation
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


# ===== User Schemas =====

class UserBase(BaseModel):
    username: str = Field(..., min_length=1, max_length=15, pattern=r"^[a-zA-Z0-9_]+$")
    display_name: str = Field(..., min_length=1, max_length=50)
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(..., min_length=8)
    display_name: Optional[str] = Field(None, max_length=50)


class UserUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=50)
    bio: Optional[str] = Field(None, max_length=160)
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    email: Optional[str] = None
    bio: Optional[str]
    avatar_url: Optional[str]
    cover_url: Optional[str]
    created_at: datetime
    verified: bool

    class Config:
        from_attributes = True


class UserPublicResponse(BaseModel):
    id: str
    username: str
    display_name: str
    bio: Optional[str]
    avatar_url: Optional[str]
    cover_url: Optional[str]
    verified: bool

    class Config:
        from_attributes = True


class UserPublicWithFollowResponse(UserPublicResponse):
    is_following: bool = False


class UserProfile(BaseModel):
    id: str
    username: str
    display_name: str
    bio: Optional[str]
    avatar_url: Optional[str]
    cover_url: Optional[str]
    verified: bool
    created_at: datetime
    followers_count: int
    following_count: int
    posts_count: int


class UserProfileEnvelope(BaseModel):
    user: UserProfile
    is_following: bool = False
    is_blocked: bool = False
    is_muted: bool = False


class UserEnvelope(BaseModel):
    user: UserResponse


class UserListResponse(BaseModel):
    users: List[UserPublicWithFollowResponse]
    total_count: int


class UserDirectoryResponse(BaseModel):
    users: List[UserResponse]
    total_count: int


class UserAutocompleteResponse(BaseModel):
    id: str
    username: str
    display_name: str
    avatar_url: Optional[str]


class UserAutocompleteListResponse(BaseModel):
    users: List[UserAutocompleteResponse]


# ===== Auth Schemas =====

class LoginRequest(BaseModel):
    email_or_username: str
    password: str


class AuthResponse(BaseModel):
    user: UserResponse


# ===== Post Schemas =====

class PostCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=280)
    parent_post_id: Optional[str] = None
    image_url: Optional[str] = None


class ParentPostPreview(BaseModel):
    id: str
    author: UserPublicResponse
    content: str


class PostResponse(BaseModel):
    id: str
    author: UserPublicResponse
    content: str
    created_at: datetime
    parent_post_id: Optional[str] = None
    reply_count: int
    repost_count: int
    like_count: int
    is_liked: bool = False
    is_reposted: bool = False
    is_repost: bool = False
    image_url: Optional[str] = None
    parent_post: Optional[ParentPostPreview] = None
    original_post: Optional["PostResponse"] = None

    class Config:
        from_attributes = True


class PostImageUploadResponse(BaseModel):
    url: str


class PostEnvelope(BaseModel):
    post: PostResponse


class PostsListResponse(BaseModel):
    posts: List[PostResponse]


class TimelineResponse(BaseModel):
    posts: List[PostResponse]
    has_more: bool


class HashtagPostsResponse(BaseModel):
    tag: str
    posts: List[PostResponse]
    has_more: bool


# ===== Notification Schemas =====

class NotificationResponse(BaseModel):
    id: str
    type: str
    actor: UserPublicResponse
    post: Optional[PostResponse]
    message_id: Optional[str] = None
    conversation_user: Optional[UserPublicResponse] = None
    created_at: datetime
    read: bool

    class Config:
        from_attributes = True


class NotificationsResponse(BaseModel):
    notifications: List[NotificationResponse]
    has_more: bool


class CountResponse(BaseModel):
    count: int


class MarkAllReadResponse(BaseModel):
    success: bool
    marked_count: int


# ===== Direct Message Schemas =====

class ConversationCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=15, pattern=r"^[a-zA-Z0-9_]+$")


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class MessageResponse(BaseModel):
    id: str
    sender_id: str
    recipient_id: str
    content: str
    created_at: datetime
    read: bool

    class Config:
        from_attributes = True


class ConversationResponse(BaseModel):
    other_user: UserPublicResponse
    last_message: MessageResponse
    unread_count: int


class ConversationsResponse(BaseModel):
    conversations: List[ConversationResponse]


class ThreadResponse(BaseModel):
    messages: List[MessageResponse]
    other_user: UserPublicResponse


class MessageEnvelope(BaseModel):
    message: MessageResponse


# ===== Search Schemas =====

class SearchUsersResponse(BaseModel):
    users: List[UserPublicWithFollowResponse]


class SearchPostsResponse(BaseModel):
    posts: List[PostResponse]


# ===== Action Response Schemas =====

class SuccessResponse(BaseModel):
    success: bool


class LikeActionResponse(BaseModel):
    success: bool
    like_count: int


class RepostActionResponse(BaseModel):
    success: bool
    repost_count: int


class FollowActionResponse(BaseModel):
    success: bool
    followers_count: int


class BlockRequest(BaseModel):
    target_user_id: str


class MuteRequest(BaseModel):
    target_user_id: str


# ===== Trends =====

class TrendResponse(BaseModel):
    id: str
    name: str
    post_count: int

    class Config:
        from_attributes = True


class TrendsResponse(BaseModel):
    trends: List[TrendResponse]


class SeedSummaryResponse(BaseModel):
    users: int
    users_with_avatar: int
    posts: int
    replies: int
    trends: int


# ===== Health =====

class HealthResponse(BaseModel):
    status: str
    timestamp: Optional[datetime] = None
