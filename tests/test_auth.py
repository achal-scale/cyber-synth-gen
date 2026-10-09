"""
Tests for authentication endpoints
"""
from fastapi import status


def test_register_success(client):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "newuser",
            "display_name": "New User",
            "email": "newuser@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["user"]["username"] == "newuser"
    assert data["user"]["display_name"] == "New User"
    assert data["user"]["email"] == "newuser@example.com"
    assert "password" not in data["user"]
    assert "access_token" in response.cookies


def test_register_duplicate_username(client, test_user):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "display_name": "Another User",
            "email": "another@example.com",
            "password": "wrongpassword",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "username" in response.json()["detail"].lower()


def test_register_duplicate_email(client, test_user):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "anotheruser",
            "display_name": "Another User",
            "email": "test@example.com",
            "password": "wrongpassword",
        },
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "email" in response.json()["detail"].lower()


def test_register_invalid_username(client):
    response = client.post(
        "/api/auth/register",
        json={
            "username": "invalid-user!",
            "display_name": "Invalid User",
            "email": "invalid@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_login_success_with_email(client, test_user):
    response = client.post(
        "/api/auth/login",
        json={
            "email_or_username": "test@example.com",
            "password": "password123",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["user"]["username"] == "testuser"
    assert "access_token" in response.cookies


def test_login_success_with_username(client, test_user):
    response = client.post(
        "/api/auth/login",
        json={
            "email_or_username": "testuser",
            "password": "password123",
        },
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["user"]["username"] == "testuser"
    assert "access_token" in response.cookies


def test_login_wrong_password(client, test_user):
    response = client.post(
        "/api/auth/login",
        json={
            "email_or_username": "testuser",
            "password": "wrongpassword",
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_login_nonexistent_user(client):
    response = client.post(
        "/api/auth/login",
        json={
            "email_or_username": "nonexistent",
            "password": "password123",
        },
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_current_user(auth_client, test_user):
    response = auth_client.get("/api/auth/me")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["user"]["username"] == test_user.username
    assert data["user"]["email"] == test_user.email


def test_get_current_user_unauthorized(client):
    response = client.get("/api/auth/me")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_logout(auth_client):
    response = auth_client.post("/api/auth/logout")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] is True
