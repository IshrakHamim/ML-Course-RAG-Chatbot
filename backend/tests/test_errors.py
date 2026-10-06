from app.core.errors import AI_BUSY_MESSAGE, AIServiceError


def test_ai_error_maps_to_503(client):
    def boom():
        raise AIServiceError("quota")

    client.app.add_api_route("/_test/ai-error", boom)
    response = client.get("/_test/ai-error")
    assert response.status_code == 503
    assert response.json() == {"detail": AI_BUSY_MESSAGE}
    assert AI_BUSY_MESSAGE == "The AI service is busy, please try again."


def test_unexpected_error_is_generic_500(client):
    def boom():
        raise RuntimeError("secret detail")

    client.app.add_api_route("/_test/crash", boom)
    response = client.get("/_test/crash")
    assert response.status_code == 500
    assert "secret detail" not in response.text
    assert "Traceback" not in response.text
    assert response.json() == {"detail": "Internal server error"}


def test_cors_allows_only_configured_origin(client):
    evil = client.get("/api/v1/health", headers={"Origin": "http://evil.test"})
    assert "access-control-allow-origin" not in evil.headers
    good = client.get("/api/v1/health", headers={"Origin": "http://localhost:5173"})
    assert good.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_unexpected_500_keeps_cors_headers(client):
    def boom():
        raise RuntimeError("secret detail")

    client.app.add_api_route("/_test/crash-cors", boom)
    response = client.get("/_test/crash-cors", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
