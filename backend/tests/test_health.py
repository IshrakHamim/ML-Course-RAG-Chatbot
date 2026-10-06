from sqlalchemy.exc import OperationalError

from app.core.db import get_db


def test_health_ok(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


class BrokenSession:
    def execute(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))


def test_health_db_down(client):
    client.app.dependency_overrides[get_db] = lambda: BrokenSession()
    response = client.get("/api/v1/health")
    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}
