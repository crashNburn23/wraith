class TestAuth:
    def test_login_ok(self, client):
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "wraith"})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_bad_credentials(self, client):
        resp = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
        assert resp.status_code == 401

    def test_protected_route_requires_token(self, client):
        resp = client.get("/api/sources")
        assert resp.status_code in (401, 403)


class TestEndpoints:
    def test_health(self, client):
        assert client.get("/api/health").status_code == 200

    def test_sources_list(self, client, auth_headers):
        resp = client.get("/api/sources", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_source_stats(self, client, auth_headers):
        resp = client.get("/api/sources/stats", headers=auth_headers)
        assert resp.status_code == 200

    def test_bulletin_today_empty(self, client, auth_headers):
        resp = client.get("/api/bulletin/today", headers=auth_headers)
        assert resp.status_code == 200

    def test_scoring_config(self, client, auth_headers):
        resp = client.get("/api/settings/scoring", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        total = (
            data["weight_ai_severity"] + data["weight_feedback_signal"]
            + data["weight_profile_match"] + data["weight_kev_bonus"] + data["weight_recency"]
        )
        assert abs(total - 1.0) < 0.001

    def test_suggest_weights_needs_data(self, client, auth_headers):
        resp = client.get("/api/settings/scoring/suggest", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["available"] is False

    def test_watchlist_crud(self, client, auth_headers):
        resp = client.post("/api/settings/watchlist", json={"item_type": "actor", "value": "Test Actor"}, headers=auth_headers)
        assert resp.status_code == 200
        item_id = resp.json()["id"]

        resp = client.get("/api/settings/watchlist", headers=auth_headers)
        assert any(i["id"] == item_id for i in resp.json())

        # duplicate add is a no-op
        resp = client.post("/api/settings/watchlist", json={"item_type": "actor", "value": "test actor"}, headers=auth_headers)
        assert resp.json()["already_existed"] is True

        resp = client.delete(f"/api/settings/watchlist/{item_id}", headers=auth_headers)
        assert resp.status_code == 200

    def test_watchlist_rejects_bad_type(self, client, auth_headers):
        resp = client.post("/api/settings/watchlist", json={"item_type": "banana", "value": "x"}, headers=auth_headers)
        assert resp.status_code == 400

    def test_enrich_status(self, client, auth_headers):
        resp = client.get("/api/enrich/status", headers=auth_headers)
        assert resp.status_code == 200

    def test_feedback_signal_transparency(self, client, auth_headers):
        resp = client.get("/api/settings/feedback-signal", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] in ("active", "inactive")
