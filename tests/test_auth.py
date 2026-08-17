def test_me_requires_auth(client):
    # No Authorization header -> should reject, not 200
    response = client.get("/api/v1/auth/me")
    assert response.status_code in (401, 403)
