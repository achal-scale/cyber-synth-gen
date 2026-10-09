"""
Tests for search endpoints
"""
from fastapi import status
from models import User


def test_search_users_by_username(client, test_user):
    response = client.get("/api/search/users?q=test")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "users" in data
    assert len(data["users"]) >= 1
    assert any(u["username"] == test_user.username for u in data["users"])


def test_search_users_by_display_name(client, db_session):
    user = User(
        username="searchuser",
        display_name="Searchable User",
        email="searchuser@example.com",
        password_hash="hash",
    )
    db_session.add(user)
    db_session.commit()

    response = client.get("/api/search/users?q=Searchable")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["users"]) >= 1
    assert any(u["display_name"] == "Searchable User" for u in data["users"])


def test_search_users_case_insensitive(client, test_user):
    response = client.get("/api/search/users?q=TEST")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["users"]) >= 1


def test_search_users_no_results(client):
    response = client.get("/api/search/users?q=nonexistentuser12345")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["users"] == []


def test_search_users_missing_query(client):
    response = client.get("/api/search/users")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_search_users_limit(client, db_session):
    for i in range(5):
        user = User(
            username=f"limituser{i}",
            display_name=f"Limit User {i}",
            email=f"limituser{i}@example.com",
            password_hash="hash",
        )
        db_session.add(user)
    db_session.commit()

    response = client.get("/api/search/users?q=limit&limit=3")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["users"]) <= 3


def test_search_posts_by_content(client, db_session, test_user):
    from models import Post

    post = Post(author_id=test_user.id, content="Searchable post content")
    db_session.add(post)
    db_session.commit()

    response = client.get("/api/search/posts?q=Searchable")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["posts"]) >= 1
    assert any("Searchable post content" == p["content"] for p in data["posts"])


def test_search_posts_by_author_username(client, db_session, test_user):
    from models import Post

    post = Post(author_id=test_user.id, content="Author searchable post")
    db_session.add(post)
    db_session.commit()

    response = client.get(f"/api/search/posts?q={test_user.username}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert any(p["id"] == post.id for p in data["posts"])


def test_search_posts_by_author_display_name(client, db_session, test_user):
    from models import Post

    post = Post(author_id=test_user.id, content="Display name searchable post")
    db_session.add(post)
    db_session.commit()

    response = client.get(f"/api/search/posts?q={test_user.display_name}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert any(p["id"] == post.id for p in data["posts"])


def test_search_posts_missing_query(client):
    response = client.get("/api/search/posts")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
