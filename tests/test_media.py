"""
Tests for media feed endpoint.
"""
from fastapi import status
from models import Post


def test_user_media_endpoint(client, db_session, test_user):
    media_post = Post(author_id=test_user.id, content="Check this", image_url="/uploads/test.jpg")
    plain_post = Post(author_id=test_user.id, content="No media here")
    db_session.add_all([media_post, plain_post])
    db_session.commit()

    response = client.get(f"/api/users/{test_user.username}/media")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["posts"]) == 1
    assert data["posts"][0]["id"] == media_post.id
