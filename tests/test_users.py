"""
Tests for user management endpoints
"""
from fastapi import status
from models import Block, Follow, Mute, Notification, Post


def test_get_user_profile(client, test_user):
    response = client.get(f"/api/users/{test_user.username}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["user"]["username"] == test_user.username
    assert data["user"]["display_name"] == test_user.display_name
    assert "followers_count" in data["user"]
    assert "following_count" in data["user"]
    assert "posts_count" in data["user"]


def test_get_nonexistent_user_profile(client):
    response = client.get("/api/users/nonexistent")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_update_profile(auth_client):
    response = auth_client.patch(
        "/api/users/me", json={"display_name": "Updated Name", "bio": "This is my bio"}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["user"]["display_name"] == "Updated Name"
    assert data["user"]["bio"] == "This is my bio"


def test_update_profile_unauthorized(client):
    response = client.patch("/api/users/me", json={"display_name": "Unauthorized"})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_user_posts(client, db_session, test_user):
    post1 = Post(author_id=test_user.id, content="Post 1")
    post2 = Post(author_id=test_user.id, content="Post 2")
    db_session.add_all([post1, post2])
    db_session.commit()

    response = client.get(f"/api/users/{test_user.username}/posts")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "posts" in data
    assert len(data["posts"]) == 2


def test_get_user_replies(client, db_session, test_user, test_post):
    reply = Post(author_id=test_user.id, content="Reply", parent_post_id=test_post.id)
    db_session.add(reply)
    db_session.commit()

    response = client.get(f"/api/users/{test_user.username}/replies")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "posts" in data
    assert len(data["posts"]) == 1
    assert data["posts"][0]["parent_post_id"] == test_post.id


def test_get_user_likes(client, db_session, test_user, test_post):
    from models import Like

    like = Like(user_id=test_user.id, post_id=test_post.id)
    db_session.add(like)
    db_session.commit()

    response = client.get(f"/api/users/{test_user.username}/likes")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "posts" in data
    assert len(data["posts"]) == 1
    assert data["posts"][0]["id"] == test_post.id


def test_get_followers(client, db_session, test_user, test_user2):
    follow = Follow(follower_id=test_user2.id, following_id=test_user.id)
    db_session.add(follow)
    db_session.commit()

    response = client.get(f"/api/users/{test_user.username}/followers")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "users" in data
    assert data["total_count"] == 1
    assert data["users"][0]["username"] == test_user2.username


def test_get_following(client, db_session, test_user, test_user2):
    follow = Follow(follower_id=test_user.id, following_id=test_user2.id)
    db_session.add(follow)
    db_session.commit()

    response = client.get(f"/api/users/{test_user.username}/following")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "users" in data
    assert data["total_count"] == 1
    assert data["users"][0]["username"] == test_user2.username


def test_follow_user(auth_client, test_user2):
    response = auth_client.post(f"/api/users/{test_user2.username}/follow")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["followers_count"] >= 1


def test_follow_user_creates_notification(auth_client, db_session, test_user, test_user2):
    response = auth_client.post(f"/api/users/{test_user2.username}/follow")

    assert response.status_code == status.HTTP_200_OK

    notification = db_session.query(Notification).filter(
        Notification.recipient_id == test_user2.id,
        Notification.actor_id == test_user.id,
        Notification.type == "follow",
    ).first()
    assert notification is not None


def test_follow_notification_visible_in_notifications_feed(auth_client, db_session, test_user, test_user2, client):
    access_token = __import__("auth").create_access_token(data={"sub": test_user.id})
    auth_client.post(f"/api/users/{test_user2.username}/follow")

    client.cookies.set("access_token", __import__("auth").create_access_token(data={"sub": test_user2.id}))
    response = client.get("/api/notifications")

    assert response.status_code == status.HTTP_200_OK
    notifications = response.json()["notifications"]
    follow_notification = next((n for n in notifications if n["type"] == "follow"), None)
    assert follow_notification is not None
    assert follow_notification["actor"]["username"] == test_user.username


def test_follow_notification_visible_in_unread_count(auth_client, test_user2, client):
    auth_client.post(f"/api/users/{test_user2.username}/follow")

    client.cookies.set("access_token", __import__("auth").create_access_token(data={"sub": test_user2.id}))
    response = client.get("/api/notifications/unread-count")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["count"] == 1


def test_follow_self(auth_client, test_user):
    response = auth_client.post(f"/api/users/{test_user.username}/follow")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_follow_already_following(auth_client, db_session, test_user, test_user2):
    follow = Follow(follower_id=test_user.id, following_id=test_user2.id)
    db_session.add(follow)
    db_session.commit()

    response = auth_client.post(f"/api/users/{test_user2.username}/follow")

    assert response.status_code == status.HTTP_200_OK


def test_unfollow_user(auth_client, db_session, test_user, test_user2):
    follow = Follow(follower_id=test_user.id, following_id=test_user2.id)
    db_session.add(follow)
    db_session.commit()

    response = auth_client.delete(f"/api/users/{test_user2.username}/follow")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] is True


def test_unfollow_not_following(auth_client, test_user2):
    response = auth_client.delete(f"/api/users/{test_user2.username}/follow")

    assert response.status_code == status.HTTP_200_OK


def test_block_user(auth_client, db_session, test_user, test_user2):
    follow = Follow(follower_id=test_user.id, following_id=test_user2.id)
    db_session.add(follow)
    db_session.commit()

    response = auth_client.post(f"/api/users/{test_user2.username}/block")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] is True

    follow_exists = db_session.query(Follow).filter(
        Follow.follower_id == test_user.id,
        Follow.following_id == test_user2.id,
    ).first()
    assert follow_exists is None


def test_block_self(auth_client, test_user):
    response = auth_client.post(f"/api/users/{test_user.username}/block")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_block_already_blocked(auth_client, db_session, test_user, test_user2):
    block = Block(blocker_id=test_user.id, blocked_id=test_user2.id)
    db_session.add(block)
    db_session.commit()

    response = auth_client.post(f"/api/users/{test_user2.username}/block")

    assert response.status_code == status.HTTP_200_OK


def test_unblock_user(auth_client, db_session, test_user, test_user2):
    block = Block(blocker_id=test_user.id, blocked_id=test_user2.id)
    db_session.add(block)
    db_session.commit()

    response = auth_client.delete(f"/api/users/{test_user2.username}/block")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] is True


def test_unblock_not_blocked(auth_client, test_user2):
    response = auth_client.delete(f"/api/users/{test_user2.username}/block")

    assert response.status_code == status.HTTP_200_OK


def test_mute_user(auth_client, test_user2):
    response = auth_client.post(f"/api/users/{test_user2.username}/mute")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] is True


def test_mute_self(auth_client, test_user):
    response = auth_client.post(f"/api/users/{test_user.username}/mute")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_mute_already_muted(auth_client, db_session, test_user, test_user2):
    mute = Mute(muter_id=test_user.id, muted_id=test_user2.id)
    db_session.add(mute)
    db_session.commit()

    response = auth_client.post(f"/api/users/{test_user2.username}/mute")

    assert response.status_code == status.HTTP_200_OK


def test_unmute_user(auth_client, db_session, test_user, test_user2):
    mute = Mute(muter_id=test_user.id, muted_id=test_user2.id)
    db_session.add(mute)
    db_session.commit()

    response = auth_client.delete(f"/api/users/{test_user2.username}/mute")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] is True


def test_unmute_not_muted(auth_client, test_user2):
    response = auth_client.delete(f"/api/users/{test_user2.username}/mute")

    assert response.status_code == status.HTTP_200_OK
