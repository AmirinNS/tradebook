def test_health_ok(client):
    """GET /health returns 200, status == 'ok', and preserves env."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["env"] == "testing"
