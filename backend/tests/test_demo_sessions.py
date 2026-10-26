from fastapi.testclient import TestClient

from app import main
from app.domain.demo_sessions import DemoSessionStore


def test_demo_session_store_uses_opaque_credentials_and_isolates_identities():
    now = [100.0]
    store = DemoSessionStore(idle_timeout_seconds=30, clock=lambda: now[0])

    first_token, first = store.create("  Priya  ")
    second_token, second = store.create("Rahul")

    assert first_token != second_token
    assert first["display_name"] == "  Priya  "
    assert first["identity_id"] != second["identity_id"]
    assert first_token not in repr(store._sessions)
    assert store.authorize(first_token)["identity_id"] == first["identity_id"]
    assert store.authorize(second_token)["identity_id"] == second["identity_id"]
    assert store.authorize("invalid-token") is None


def test_demo_session_store_refreshes_and_expires_after_idle_timeout():
    now = [0.0]
    store = DemoSessionStore(idle_timeout_seconds=30, clock=lambda: now[0])
    token, session = store.create("Aria Tester")

    now[0] = 20.0
    assert store.authorize(token)["identity_id"] == session["identity_id"]
    now[0] = 49.0
    assert store.authorize(token) is not None
    now[0] = 79.0
    assert store.authorize(token) is None
    assert len(store) == 0


def test_demo_session_store_purges_expired_sessions_on_create():
    now = [0.0]
    store = DemoSessionStore(idle_timeout_seconds=30, clock=lambda: now[0])
    old_token, _ = store.create("Old")
    now[0] = 30.0

    new_token, _ = store.create("New")

    assert store.authorize(old_token) is None
    assert store.authorize(new_token) is not None
    assert len(store) == 1


def test_demo_account_and_mock_context_sessions_are_mode_isolated():
    store = DemoSessionStore()
    account_token, account = store.create("Priya")
    mock_token, mock = store.create_mock_context()

    assert account["mode"] == "account"
    assert account["orders"] == []
    assert mock["mode"] == "mock_db"
    assert mock["display_name"] is None
    assert store.authorize(account_token, expected_mode="mock_db") is None
    assert store.authorize(mock_token, expected_mode="account") is None

    assert store.update_context(
        mock_token, expected_mode="mock_db", context={"last_order_id": "ORD-101"}
    )
    assert store.authorize(mock_token, expected_mode="mock_db")["conversation_context"] == {
        "last_order_id": "ORD-101"
    }
    assert store.authorize(account_token, expected_mode="account")["conversation_context"] == {}


def test_create_demo_session_validates_name_and_disables_caching(monkeypatch):
    monkeypatch.setattr(main.app.state, "demo_session_store", DemoSessionStore())
    with TestClient(main.app) as client:
        response = client.post("/api/demo-sessions", json={"name": "  Priya Sharma  "})

        assert response.status_code == 201
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert body["display_name"] == "Priya Sharma"
        assert isinstance(body["credential"], str)
        assert len(body["credential"]) >= 40
        assert main.app.state.demo_session_store.authorize(body["credential"])["display_name"] == "Priya Sharma"

        assert client.post("/api/demo-sessions", json={"name": "   "}).status_code == 422
        assert client.post("/api/demo-sessions", json={"name": "Valid", "extra": True}).status_code == 422


def test_create_demo_session_supports_configured_browser_origin():
    with TestClient(main.app) as client:
        response = client.options(
            "/api/demo-sessions",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-credentials" not in response.headers


def test_create_demo_session_cors_rejects_unconfigured_origin():
    with TestClient(main.app) as client:
        response = client.options(
            "/api/demo-sessions",
            headers={
                "Origin": "https://untrusted.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_create_mock_context_returns_no_store_mode_bound_token(monkeypatch):
    store = DemoSessionStore()
    monkeypatch.setattr(main.app.state, "demo_session_store", store)
    with TestClient(main.app) as client:
        response = client.post("/api/mock-sessions")

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    context_id = response.json()["context_id"]
    assert store.authorize(context_id, expected_mode="mock_db")["mode"] == "mock_db"
    assert store.authorize(context_id, expected_mode="account") is None
