from app.config import settings


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"] == "test"
    assert "instance" in body


def test_version(client):
    assert client.get("/version").json()["version"] == "test"


def test_crud(client):
    assert client.get("/api/tasks").json() == []
    created = client.post("/api/tasks", json={"title": "Write Dockerfile"})
    assert created.status_code == 201
    task_id = created.json()["id"]

    assert client.get(f"/api/tasks/{task_id}").json()["title"] == "Write Dockerfile"

    updated = client.put(f"/api/tasks/{task_id}", json={"title": "Write Dockerfile", "done": True})
    assert updated.json()["done"] is True

    assert client.delete(f"/api/tasks/{task_id}").status_code == 204
    assert client.get(f"/api/tasks/{task_id}").status_code == 404


def test_validation(client):
    assert client.post("/api/tasks", json={"title": ""}).status_code == 422


def test_metrics_use_route_template(client):
    client.get("/api/tasks/12345")
    text = client.get("/metrics").text
    assert 'route="/api/tasks/{task_id}"' in text
    assert "http_request_duration_seconds_bucket" in text
    assert "/api/tasks/12345" not in text


def test_fail_rate(client, monkeypatch):
    monkeypatch.setattr(settings, "fail_rate", 1.0)
    assert client.get("/api/tasks").status_code == 500
    assert client.get("/health").status_code == 200


def test_injected_failure_keeps_route_template(client, monkeypatch):
    monkeypatch.setattr(settings, "fail_rate", 1.0)
    client.get("/api/tasks/777")
    text = client.get("/metrics").text
    assert 'route="/api/tasks/{task_id}",status="500"' in text
    assert "/api/tasks/777" not in text
