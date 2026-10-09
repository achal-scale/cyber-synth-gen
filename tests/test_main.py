"""
Tests for main application endpoints.
"""
from fastapi import status


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data


def test_root_metadata_mentions_w(client):
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["name"] == "W"
    assert data["status"] == "running"
    assert data["health"] == "/api/health"
