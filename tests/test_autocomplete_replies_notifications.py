"""
Tests for user autocomplete, replies parent preview, and DM notifications.
"""
from fastapi import status
from models import DirectMessage, Notification, Post


def test_autocomplete_users(client, db_session, test_user, test_user2):
    response = client.get("/api/users/autocomplete?q=test")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    usernames = {user["username"] for user in data["users"]}
    assert test_user.username in usernames
    assert test_user2.username in usernames


def test_replies_include_parent_preview(client, db_session, test_user, test_post):
    reply = Post(author_id=test_user.id, content="Reply", parent_post_id=test_post.id)
    db_session.add(reply)
    db_session.commit()

    response = client.get(f"/api/users/{test_user.username}/replies")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["posts"]) == 1
    post = data["posts"][0]
    assert post["parent_post_id"] == test_post.id
    assert post["parent_post"] is not None
    assert post["parent_post"]["id"] == test_post.id


def test_send_message_creates_notification(auth_client, db_session, test_user2):
    response = auth_client.post(
        f"/api/messages/conversations/{test_user2.username}",
        json={"content": "Hello from DM"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    message_id = response.json()["message"]["id"]

    notification = db_session.query(Notification).filter(
        Notification.recipient_id == test_user2.id,
        Notification.type == "dm",
    ).first()
    assert notification is not None
    assert notification.message_id == message_id


def test_notifications_include_dm_fields(auth_client, db_session, test_user, test_user2):
    message = DirectMessage(sender_id=test_user2.id, recipient_id=test_user.id, content="Hello")
    db_session.add(message)
    db_session.commit()
    db_session.refresh(message)

    notification = Notification(
        recipient_id=test_user.id,
        actor_id=test_user2.id,
        type="dm",
        message_id=message.id,
    )
    db_session.add(notification)
    db_session.commit()

    response = auth_client.get("/api/notifications")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    notif_data = next(item for item in data["notifications"] if item["type"] == "dm")
    assert notif_data["message_id"] == message.id
    assert notif_data["conversation_user"]["username"] == test_user2.username
