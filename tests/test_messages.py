"""
Tests for direct messaging endpoints
"""
from fastapi import status
from models import DirectMessage


def test_send_message(auth_client, test_user2):
    response = auth_client.post(
        f"/api/messages/conversations/{test_user2.username}",
        json={"content": "Hello, this is a test message!"},
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()["message"]
    assert data["content"] == "Hello, this is a test message!"
    assert data["recipient_id"] == test_user2.id
    assert data["read"] is False


def test_send_message_to_self(auth_client, test_user):
    response = auth_client.post(
        f"/api/messages/conversations/{test_user.username}",
        json={"content": "Message to myself"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_send_message_to_nonexistent_user(auth_client):
    response = auth_client.post(
        "/api/messages/conversations/nonexistentuser",
        json={"content": "Message to nobody"},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_send_message_unauthorized(client, test_user2):
    response = client.post(
        f"/api/messages/conversations/{test_user2.username}",
        json={"content": "Unauthorized message"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_send_empty_message(auth_client, test_user2):
    response = auth_client.post(
        f"/api/messages/conversations/{test_user2.username}",
        json={"content": ""},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_get_conversations(auth_client, db_session, test_user, test_user2):
    msg1 = DirectMessage(sender_id=test_user.id, recipient_id=test_user2.id, content="Message 1")
    msg2 = DirectMessage(sender_id=test_user2.id, recipient_id=test_user.id, content="Message 2")
    db_session.add_all([msg1, msg2])
    db_session.commit()

    response = auth_client.get("/api/messages/conversations")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["conversations"]
    assert len(data) == 1
    assert data[0]["other_user"]["username"] == test_user2.username
    assert data[0]["last_message"]["content"] == "Message 2"


def test_get_conversations_unauthorized(client):
    response = client.get("/api/messages/conversations")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_message_thread(auth_client, db_session, test_user, test_user2):
    msg1 = DirectMessage(sender_id=test_user.id, recipient_id=test_user2.id, content="First message")
    msg2 = DirectMessage(sender_id=test_user2.id, recipient_id=test_user.id, content="Reply message")
    db_session.add_all([msg1, msg2])
    db_session.commit()

    response = auth_client.get(f"/api/messages/conversations/{test_user2.username}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "messages" in data
    assert len(data["messages"]) == 2
    assert data["other_user"]["username"] == test_user2.username
    assert data["messages"][0]["content"] == "First message"
    assert data["messages"][1]["content"] == "Reply message"


def test_get_message_thread_marks_as_read(auth_client, db_session, test_user, test_user2):
    msg = DirectMessage(
        sender_id=test_user2.id,
        recipient_id=test_user.id,
        content="Unread message",
        read=False,
    )
    db_session.add(msg)
    db_session.commit()
    db_session.refresh(msg)

    response = auth_client.get(f"/api/messages/conversations/{test_user2.username}")

    assert response.status_code == status.HTTP_200_OK

    db_session.refresh(msg)
    assert msg.read is True


def test_get_message_thread_nonexistent_user(auth_client):
    response = auth_client.get("/api/messages/conversations/nonexistentuser")

    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_unread_message_count(auth_client, db_session, test_user, test_user2):
    msg1 = DirectMessage(sender_id=test_user2.id, recipient_id=test_user.id, content="Unread 1", read=False)
    msg2 = DirectMessage(sender_id=test_user2.id, recipient_id=test_user.id, content="Unread 2", read=False)
    msg3 = DirectMessage(sender_id=test_user2.id, recipient_id=test_user.id, content="Read message", read=True)
    db_session.add_all([msg1, msg2, msg3])
    db_session.commit()

    response = auth_client.get("/api/messages/unread-count")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["count"] == 2


def test_conversation_unread_count(auth_client, db_session, test_user, test_user2):
    msg1 = DirectMessage(sender_id=test_user2.id, recipient_id=test_user.id, content="Unread 1", read=False)
    msg2 = DirectMessage(sender_id=test_user2.id, recipient_id=test_user.id, content="Unread 2", read=False)
    db_session.add_all([msg1, msg2])
    db_session.commit()

    response = auth_client.get("/api/messages/conversations")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["conversations"]
    assert len(data) == 1
    assert data[0]["unread_count"] == 2
