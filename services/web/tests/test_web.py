from unittest.mock import MagicMock, patch

import pytest
import requests

from app.main import app


@pytest.fixture()
def client():
    app.config["TESTING"] = True
    return app.test_client()


def fake_response(payload):
    resp = MagicMock()
    resp.json.return_value = payload
    return resp


def test_health(client):
    assert client.get("/health").json["status"] == "ok"


@patch("app.main.requests.request")
def test_index_lists_tasks(mock_request, client):
    mock_request.side_effect = [
        fake_response([{"id": 1, "title": "Купити молоко", "done": False}]),
        fake_response({"version": "1.0.0", "instance": "api-1"}),
    ]
    page = client.get("/").get_data(as_text=True)
    assert "Купити молоко" in page
    assert "api 1.0.0" in page


@patch("app.main.requests.request", side_effect=requests.ConnectionError())
def test_index_api_down(_mock, client):
    page = client.get("/").get_data(as_text=True)
    assert "API недоступний" in page


@patch("app.main.requests.request")
def test_create_posts_to_api(mock_request, client):
    resp = client.post("/tasks", data={"title": "New"})
    assert resp.status_code == 302
    method, url = mock_request.call_args.args
    assert method == "POST" and url.endswith("/api/tasks")
    assert mock_request.call_args.kwargs["json"] == {"title": "New"}
