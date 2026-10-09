"""
Tests for notification endpoints
"""
from fastapi import status
from models import Notification


def test_get_notifications(auth_client, db_session, test_user, test_user2):
    notification = Notification(
        recipient_id=test_user.id,
        actor_id=test_user2.id,
        type="follow",
    )
    db_session.add(notification)
    db_session.commit()

    response = auth_client.get("/api/notifications")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "notifications" in data
    assert len(data["notifications"]) == 1
    assert data["notifications"][0]["type"] == "follow"
    assert data["notifications"][0]["actor"]["username"] == test_user2.username


def test_get_notifications_unauthorized(client):
    response = client.get("/api/notifications")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_notifications_with_post(auth_client, db_session, test_user, test_user2, test_post):
    notification = Notification(
        recipient_id=test_user.id,
        actor_id=test_user2.id,
        type="like",
        post_id=test_post.id,
    )
    db_session.add(notification)
    db_session.commit()

    response = auth_client.get("/api/notifications")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["notifications"]) == 1
    assert data["notifications"][0]["type"] == "like"
    assert data["notifications"][0]["post"] is not None
    assert data["notifications"][0]["post"]["id"] == test_post.id


def test_mark_notification_read(auth_client, db_session, test_user, test_user2):
    notification = Notification(
        recipient_id=test_user.id,
        actor_id=test_user2.id,
        type="follow",
        read=False,
    )
    db_session.add(notification)
    db_session.commit()
    db_session.refresh(notification)

    response = auth_client.post(f"/api/notifications/{notification.id}/read")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] is True

    db_session.refresh(notification)
    assert notification.read is True


def test_mark_notification_read_not_found(auth_client):
    response = auth_client.post("/api/notifications/nonexistent/read")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_mark_notification_read_not_owner(auth_client, db_session, test_user, test_user2):
    notification = Notification(
        recipient_id=test_user2.id,
        actor_id=test_user.id,
        type="follow",
    )
    db_session.add(notification)
    db_session.commit()
    db_session.refresh(notification)

    response = auth_client.post(f"/api/notifications/{notification.id}/read")

    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_mark_all_notifications_read(auth_client, db_session, test_user, test_user2):
    for _ in range(3):
        notification = Notification(
            recipient_id=test_user.id,
            actor_id=test_user2.id,
            type="follow",
            read=False,
        )
        db_session.add(notification)
    db_session.commit()

    response = auth_client.post("/api/notifications/mark-all-read")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["success"] is True
    assert data["marked_count"] == 3

    unread_count = db_session.query(Notification).filter(
        Notification.recipient_id == test_user.id,
        Notification.read.is_(False),
    ).count()
    assert unread_count == 0


def test_get_unread_count(auth_client, db_session, test_user, test_user2):
    for _ in range(3):
        notification = Notification(
            recipient_id=test_user.id,
            actor_id=test_user2.id,
            type="follow",
            read=False,
        )
        db_session.add(notification)

    read_notification = Notification(
        recipient_id=test_user.id,
        actor_id=test_user2.id,
        type="follow",
        read=True,
    )
    db_session.add(read_notification)
    db_session.commit()

    response = auth_client.get("/api/notifications/unread-count")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["count"] == 3


def test_notifications_pagination(auth_client, db_session, test_user, test_user2):
    for _ in range(25):
        notification = Notification(
            recipient_id=test_user.id,
            actor_id=test_user2.id,
            type="follow",
        )
        db_session.add(notification)
    db_session.commit()

    response = auth_client.get("/api/notifications?limit=20")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["notifications"]) == 20
    assert data["has_more"] is True
