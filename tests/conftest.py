"""
Pytest configuration and fixtures for backend tests.
"""
import os
import sys
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

UPLOAD_ROOT = os.path.join(tempfile.gettempdir(), "w_uploads_test")
os.environ["UPLOAD_ROOT"] = UPLOAD_ROOT
os.makedirs(UPLOAD_ROOT, exist_ok=True)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import create_access_token, hash_password
from models import Base, Post, User


@pytest.fixture(scope="function")
def test_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db_session(test_engine):
    TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session = TestSessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(test_engine):
    from main import app
    from database import get_db

    def override_get_db():
        TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
        session = TestSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture(scope="function")
def test_user(db_session):
    user = User(
        username="testuser",
        display_name="Test User",
        email="test@example.com",
        password_hash=hash_password("password123"),
        bio="This is a test user on W",
        avatar_url="https://example.com/avatar.jpg",
        verified=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def test_user2(db_session):
    user = User(
        username="testuser2",
        display_name="Test User 2",
        email="test2@example.com",
        password_hash=hash_password("password123"),
        bio="This is test user 2 on W",
        avatar_url="https://example.com/avatar2.jpg",
        verified=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture(scope="function")
def test_post(db_session, test_user):
    post = Post(author_id=test_user.id, content="This is a test post on W!")
    db_session.add(post)
    db_session.commit()
    db_session.refresh(post)
    return post


@pytest.fixture(scope="function")
def auth_client(client, test_user):
    access_token = create_access_token(data={"sub": test_user.id})
    client.cookies.set("access_token", access_token)
    return client


@pytest.fixture(scope="function")
def sample_user(test_user):
    return test_user


@pytest.fixture(scope="function")
def sample_post(test_post):
    return test_post
