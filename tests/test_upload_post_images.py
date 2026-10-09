"""
Tests for post image upload endpoint.
"""
from fastapi import status


def test_upload_post_image_success(auth_client, test_user, tmp_path):
    file_path = tmp_path / "post.jpg"
    file_path.write_bytes(b"fake image data")

    with file_path.open("rb") as file_obj:
        response = auth_client.post(
            "/api/posts/images",
            files={"file": ("post.jpg", file_obj, "image/jpeg")},
        )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["url"].startswith(f"/uploads/{test_user.id}/posts/")


def test_upload_post_image_alias_success(auth_client, test_user, tmp_path):
    file_path = tmp_path / "post.jpg"
    file_path.write_bytes(b"fake image data")

    with file_path.open("rb") as file_obj:
        response = auth_client.post(
            "/api/posts/upload-image",
            files={"file": ("post.jpg", file_obj, "image/jpeg")},
        )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["url"].startswith(f"/uploads/{test_user.id}/posts/")


def test_upload_post_image_invalid_type(auth_client, tmp_path):
    file_path = tmp_path / "post.txt"
    file_path.write_text("not an image")

    with file_path.open("rb") as file_obj:
        response = auth_client.post(
            "/api/posts/images",
            files={"file": ("post.txt", file_obj, "text/plain")},
        )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
