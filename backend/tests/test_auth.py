from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends
from sqlalchemy import select

from app.api.deps import require_admin
from app.core.config import get_settings
from app.models import User


def register(client, email="bob@example.com", password="password123", **extra):
    return client.post(
        "/api/v1/auth/register", json={"email": email, "password": password, **extra}
    )


def test_register_returns_token_and_user(client):
    response = register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "bob@example.com"
    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "bob@example.com"


def test_register_creates_user_role(client, db):
    response = register(client, role="admin")
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "user"
    assert db.scalar(select(User.role)) == "user"


def test_register_normalizes_email(client, db):
    assert register(client, email=" Bob@Example.COM ").status_code == 201
    assert db.scalar(select(User.email)) == "bob@example.com"


def test_register_duplicate_email_409(client):
    assert register(client).status_code == 201
    response = register(client, email="BOB@example.com")
    assert response.status_code == 409


def test_password_too_short_422(client):
    assert register(client, password="1234567").status_code == 422


def test_password_over_72_bytes_422(client):
    assert register(client, password="é" * 37).status_code == 422


def test_invalid_email_422(client):
    assert register(client, email="not-an-email").status_code == 422


def test_login_success(client, make_user):
    make_user("amy@example.com", password="password123")
    response = client.post(
        "/api/v1/auth/login", json={"email": "AMY@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    assert response.json()["user"]["email"] == "amy@example.com"


def test_login_wrong_password_and_unknown_email_same_401(client, make_user):
    make_user("amy@example.com", password="password123")
    wrong = client.post(
        "/api/v1/auth/login", json={"email": "amy@example.com", "password": "nope12345"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "ghost@example.com", "password": "password123"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}


def test_me_requires_token(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_expired_token_401(client, make_user):
    user = make_user()
    past = datetime.now(UTC) - timedelta(minutes=5)
    token = jwt.encode(
        {"sub": str(user.id), "iat": past - timedelta(hours=1), "exp": past},
        get_settings().jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_garbage_token_401(client):
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer abc"})
    assert response.status_code == 401


def test_token_with_wrong_secret_401(client, make_user):
    user = make_user()
    token = jwt.encode({"sub": str(user.id), "exp": 9999999999}, "w" * 40, algorithm="HS256")
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_token_for_deleted_user_401(client, db, make_user, token_for):
    user = make_user()
    token = token_for(user)
    db.delete(user)
    db.commit()
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_require_admin_403(client, user, admin):
    def admin_only(current=Depends(require_admin)):
        return {"ok": True}

    client.app.add_api_route("/_test/admin-only", admin_only)
    assert client.get("/_test/admin-only", headers=user).status_code == 403
    assert client.get("/_test/admin-only", headers=admin).status_code == 200


def test_create_admin_creates_new_admin(db, monkeypatch):
    from app import cli

    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "adminpass123")
    assert cli.main(["create-admin", "--email", "Root@Example.com"]) == 0
    assert db.scalar(select(User.role).where(User.email == "root@example.com")) == "admin"


def test_create_admin_promotes_existing_user(db, make_user, monkeypatch):
    from app import cli
    from app.core.security import verify_password

    make_user("amy@example.com")
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": "newpassword1")
    assert cli.main(["create-admin", "--email", "amy@example.com"]) == 0
    db.expire_all()
    amy = db.scalar(select(User).where(User.email == "amy@example.com"))
    assert amy.role == "admin"
    assert verify_password("newpassword1", amy.password_hash)


def test_create_admin_rejects_mismatched_passwords(db, monkeypatch):
    from app import cli

    answers = iter(["adminpass123", "different123"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt="": next(answers))
    assert cli.main(["create-admin", "--email", "root@example.com"]) == 1
    assert db.scalar(select(User)) is None
