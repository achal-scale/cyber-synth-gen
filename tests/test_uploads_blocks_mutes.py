"""
Tests for uploads, block/mute endpoints, and timeline filtering.
"""
from fastapi import status
from models import Block, Follow, Mute, Post


def test_upload_avatar(auth_client, test_user, tmp_path, db_session):
    file_path = tmp_path / "avatar.jpg"
    file_path.write_bytes(b"fake image data")

    with file_path.open("rb") as file_obj:
        response = auth_client.post(
            f"/api/users/{test_user.id}/avatar",
            files={"file": ("avatar.jpg", file_obj, "image/jpeg")},
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["user"]
    assert data["avatar_url"] == f"/uploads/{test_user.id}/avatar.jpg"


def test_upload_cover(auth_client, test_user, tmp_path, db_session):
    file_path = tmp_path / "cover.jpg"
    file_path.write_bytes(b"fake image data")

    with file_path.open("rb") as file_obj:
        response = auth_client.post(
            f"/api/users/{test_user.id}/cover",
            files={"file": ("cover.jpg", file_obj, "image/jpeg")},
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()["user"]
    assert data["cover_url"] == f"/uploads/{test_user.id}/cover.jpg"


def test_upload_invalid_file(auth_client, test_user, tmp_path):
    file_path = tmp_path / "bad.txt"
    file_path.write_text("not an image")

    with file_path.open("rb") as file_obj:
        response = auth_client.post(
            f"/api/users/{test_user.id}/avatar",
            files={"file": ("bad.txt", file_obj, "text/plain")},
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_block_user_by_id(auth_client, db_session, test_user, test_user2):
    response = auth_client.post(
        f"/api/blocks?user_id={test_user.id}",
        json={"target_user_id": test_user2.id},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] is True
    block = db_session.query(Block).filter(
        Block.blocker_id == test_user.id,
        Block.blocked_id == test_user2.id,
    ).first()
    assert block is not None


def test_unblock_user_by_id(auth_client, db_session, test_user, test_user2):
    db_session.add(Block(blocker_id=test_user.id, blocked_id=test_user2.id))
    db_session.commit()

    response = auth_client.delete(
        f"/api/blocks?user_id={test_user.id}&target_user_id={test_user2.id}"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] is True
    block = db_session.query(Block).filter(
        Block.blocker_id == test_user.id,
        Block.blocked_id == test_user2.id,
    ).first()
    assert block is None


def test_mute_user_by_id(auth_client, db_session, test_user, test_user2):
    response = auth_client.post(
        f"/api/mutes?user_id={test_user.id}",
        json={"target_user_id": test_user2.id},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] is True
    mute = db_session.query(Mute).filter(
        Mute.muter_id == test_user.id,
        Mute.muted_id == test_user2.id,
    ).first()
    assert mute is not None


def test_unmute_user_by_id(auth_client, db_session, test_user, test_user2):
    db_session.add(Mute(muter_id=test_user.id, muted_id=test_user2.id))
    db_session.commit()

    response = auth_client.delete(
        f"/api/mutes?user_id={test_user.id}&target_user_id={test_user2.id}"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["success"] is True
    mute = db_session.query(Mute).filter(
        Mute.muter_id == test_user.id,
        Mute.muted_id == test_user2.id,
    ).first()
    assert mute is None


def test_user_timeline_filter(auth_client, db_session, test_user, test_user2):
    db_session.add(Follow(follower_id=test_user.id, following_id=test_user2.id))
    post = Post(author_id=test_user2.id, content="Muted post")
    db_session.add(post)
    db_session.add(Mute(muter_id=test_user.id, muted_id=test_user2.id))
    db_session.commit()

    response = auth_client.get(f"/api/users/{test_user.id}/timeline?filter=following")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["posts"] == []


def test_user_timeline_for_you(auth_client, db_session, test_user, test_user2):
    post = Post(author_id=test_user2.id, content="Public post")
    db_session.add(post)
    db_session.commit()

    response = auth_client.get(f"/api/users/{test_user.id}/timeline?filter=for_you")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["posts"]) == 1
