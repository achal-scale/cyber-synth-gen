"""
Tests for hashtag posts endpoint.
"""
from fastapi import status
from models import Block, Mute, Post


def test_get_hashtag_posts(auth_client, db_session, test_user, test_user2):
    post1 = Post(author_id=test_user.id, content="Hello #AI")
    post2 = Post(author_id=test_user2.id, content="Other #AI content")
    db_session.add_all([post1, post2])
    db_session.commit()

    response = auth_client.get("/api/posts/hashtags/AI")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["tag"] == "ai"
    assert len(data["posts"]) == 2


def test_get_hashtag_posts_excludes_blocked(auth_client, db_session, test_user, test_user2):
    post1 = Post(author_id=test_user2.id, content="Blocked #AI content")
    db_session.add(post1)
    db_session.add(Block(blocker_id=test_user.id, blocked_id=test_user2.id))
    db_session.commit()

    response = auth_client.get("/api/posts/hashtags/ai")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["posts"] == []


def test_get_hashtag_posts_excludes_muted(auth_client, db_session, test_user, test_user2):
    post1 = Post(author_id=test_user2.id, content="Muted #AI content")
    db_session.add(post1)
    db_session.add(Mute(muter_id=test_user.id, muted_id=test_user2.id))
    db_session.commit()

    response = auth_client.get("/api/posts/hashtags/ai")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["posts"] == []


def test_get_hashtag_posts_invalid_tag(auth_client):
    response = auth_client.get("/api/posts/hashtags/invalid-tag!")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_hashtag_posts_unauthorized(client):
    response = client.get("/api/posts/hashtags/ai")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
