"""
Tests for post management endpoints
"""
from fastapi import status
from models import Like, Post, Repost, Follow, Trend, Notification


def test_create_post(auth_client, test_user):
    response = auth_client.post("/api/posts", json={"content": "This is my first post!"})

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()["post"]
    assert data["content"] == "This is my first post!"
    assert data["author"]["username"] == test_user.username
    assert data["parent_post_id"] is None
    assert data["like_count"] == 0
    assert data["repost_count"] == 0
    assert data["reply_count"] == 0
    assert data["is_repost"] is False
    assert data["original_post"] is None


def test_create_reply(auth_client, test_post):
    response = auth_client.post(
        "/api/posts", json={"content": "This is a reply", "parent_post_id": test_post.id}
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()["post"]
    assert data["content"] == "This is a reply"
    assert data["parent_post_id"] == test_post.id


def test_create_post_too_long(auth_client):
    long_content = "x" * 281
    response = auth_client.post("/api/posts", json={"content": long_content})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_create_post_empty(auth_client):
    response = auth_client.post("/api/posts", json={"content": ""})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_create_post_unauthorized(client):
    response = client.post("/api/posts", json={"content": "Unauthorized post"})

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_post(client, test_post):
    response = client.get(f"/api/posts/{test_post.id}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["post"]
    assert data["id"] == test_post.id
    assert data["content"] == test_post.content


def test_get_nonexistent_post(client):
    response = client.get("/api/posts/nonexistent-id")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_delete_post(auth_client, test_post):
    response = auth_client.delete(f"/api/posts/{test_post.id}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] is True


def test_delete_post_not_owner(auth_client, db_session, test_user2):
    post = Post(author_id=test_user2.id, content="User 2's post")
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)

    response = auth_client.delete(f"/api/posts/{post.id}")

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_like_post(auth_client, test_post):
    response = auth_client.post(f"/api/posts/{test_post.id}/like")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["like_count"] == 1


def test_like_post_already_liked(auth_client, test_post, db_session, test_user):
    like = Like(user_id=test_user.id, post_id=test_post.id)
    db_session.add(like)
    db_session.commit()

    response = auth_client.post(f"/api/posts/{test_post.id}/like")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["like_count"] == 1


def test_unlike_post(auth_client, test_post, db_session, test_user):
    like = Like(user_id=test_user.id, post_id=test_post.id)
    db_session.add(like)
    db_session.commit()

    response = auth_client.delete(f"/api/posts/{test_post.id}/like")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["like_count"] == 0


def test_unlike_post_not_liked(auth_client, test_post):
    response = auth_client.delete(f"/api/posts/{test_post.id}/like")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_repost(auth_client, test_post):
    response = auth_client.post(f"/api/posts/{test_post.id}/repost")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["repost_count"] == 1


def test_repost_creates_post_row(auth_client, db_session, test_user, test_post):
    response = auth_client.post(f"/api/posts/{test_post.id}/repost")

    assert response.status_code == status.HTTP_200_OK
    repost_post = db_session.query(Post).filter(
        Post.author_id == test_user.id,
        Post.is_repost.is_(True),
        Post.original_post_id == test_post.id,
    ).first()
    assert repost_post is not None


def test_repost_already_reposted(auth_client, test_post, db_session, test_user):
    repost = Repost(user_id=test_user.id, post_id=test_post.id)
    db_session.add(repost)
    db_session.commit()

    response = auth_client.post(f"/api/posts/{test_post.id}/repost")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["repost_count"] == 1


def test_unrepost(auth_client, test_post, db_session, test_user):
    repost = Repost(user_id=test_user.id, post_id=test_post.id)
    db_session.add(repost)
    db_session.commit()

    response = auth_client.delete(f"/api/posts/{test_post.id}/repost")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["repost_count"] == 0


def test_get_timeline(auth_client, db_session, test_user, test_user2):
    follow = Follow(follower_id=test_user.id, following_id=test_user2.id)
    db_session.add(follow)

    post1 = Post(author_id=test_user.id, content="My post")
    post2 = Post(author_id=test_user2.id, content="Followed user's post")
    db_session.add_all([post1, post2])
    db_session.commit()

    response = auth_client.get("/api/posts/timeline")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "posts" in data
    assert len(data["posts"]) == 2


def test_get_timeline_unauthorized(client):
    response = client.get("/api/posts/timeline")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_post_replies(client, db_session, test_post, test_user):
    reply = Post(author_id=test_user.id, content="Reply", parent_post_id=test_post.id)
    db_session.add(reply)
    db_session.commit()

    response = client.get(f"/api/posts/{test_post.id}/replies")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "posts" in data
    assert len(data["posts"]) == 1
    assert data["posts"][0]["parent_post_id"] == test_post.id


def test_get_timeline_for_you(auth_client, db_session, test_user, test_user2):
    follow = Follow(follower_id=test_user.id, following_id=test_user2.id)
    db_session.add(follow)
    post1 = Post(author_id=test_user.id, content="My post")
    post2 = Post(author_id=test_user2.id, content="Followed post")
    db_session.add_all([post1, post2])
    db_session.commit()

    response = auth_client.get("/api/posts/timeline?filter=for_you")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["posts"]) == 2


def test_create_post_trends_mentions(auth_client, db_session, test_user2):
    response = auth_client.post(
        "/api/posts",
        json={"content": f"Hello @{test_user2.username} #AI #fastapi"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    trends = {trend.name for trend in db_session.query(Trend).all()}
    assert "#ai" in trends

    notification = db_session.query(Notification).filter(
        Notification.recipient_id == test_user2.id,
        Notification.type == "mention",
    ).first()
    assert notification is not None


def test_create_post_mentions_case_insensitive_user_lookup(client, db_session, test_user, test_user2):
    access_token = __import__("auth").create_access_token(data={"sub": test_user.id})
    client.cookies.set("access_token", access_token)

    response = client.post(
        "/api/posts",
        json={"content": f"Hello @{test_user2.username.upper()}"},
    )

    assert response.status_code == status.HTTP_201_CREATED

    notification = db_session.query(Notification).filter(
        Notification.recipient_id == test_user2.id,
        Notification.type == "mention",
    ).first()
    assert notification is not None
    assert notification.actor_id == test_user.id
