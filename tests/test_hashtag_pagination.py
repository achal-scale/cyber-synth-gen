"""
Tests for hashtag pagination.
"""
from fastapi import status
from models import Post


def test_hashtag_posts_pagination(auth_client, db_session, test_user):
    post1 = Post(author_id=test_user.id, content="First #AI")
    post2 = Post(author_id=test_user.id, content="Second #AI")
    db_session.add_all([post1, post2])
    db_session.commit()

    response = auth_client.get("/api/posts/hashtags/ai?limit=1")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["posts"]) == 1
    assert data["has_more"] is True
