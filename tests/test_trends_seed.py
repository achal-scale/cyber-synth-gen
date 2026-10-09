"""
Tests for trends and seed summary endpoints.
"""
from fastapi import status
from models import Post, Trend, User


def test_list_trends(client, db_session):
    trend1 = Trend(name="#Python", post_count=120)
    trend2 = Trend(name="#FastAPI", post_count=80)
    db_session.add_all([trend1, trend2])
    db_session.commit()

    response = client.get("/api/trends")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["trends"]
    assert len(data) == 2
    assert data[0]["post_count"] >= data[1]["post_count"]


def test_seed_summary(client, db_session):
    user = User(
        username="seeduser",
        display_name="Seed User",
        email="seed@example.com",
        password_hash="hash",
        avatar_url="/uploads/seed/avatar.jpg",
    )
    other = User(
        username="seeduser2",
        display_name="Seed User 2",
        email="seed2@example.com",
        password_hash="hash",
    )
    db_session.add_all([user, other])
    db_session.commit()

    post = Post(author_id=user.id, content="Seed post")
    db_session.add(post)
    db_session.commit()

    reply = Post(author_id=user.id, content="Seed reply", parent_post_id=post.id)
    db_session.add(reply)

    trend = Trend(name="#Seed", post_count=10)
    db_session.add(trend)
    db_session.commit()

    response = client.get("/api/seed/summary")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["users"] == 2
    assert data["users_with_avatar"] == 1
    assert data["posts"] == 2
    assert data["replies"] == 1
    assert data["trends"] == 1
