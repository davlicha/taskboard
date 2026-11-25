"""Бізнес-логіка, незалежна від середовища виконання.

Використовується і Lambda-обробником (ЛР-8), і контейнерною версією застосунку (ЛР-9, ЛР-10).
"""

import json
import os
import uuid
from datetime import UTC, datetime

import boto3
from botocore.exceptions import ClientError

TABLE_NAME = os.getenv("TABLE_NAME", "items")


def _table():
    # У LocalStack змінна AWS_ENDPOINT_URL встановлюється автоматично для Lambda;
    # для контейнера (ЛР-9) її задаємо в docker-compose.
    return boto3.resource("dynamodb").Table(TABLE_NAME)


def ensure_table() -> None:
    client = boto3.client("dynamodb")
    try:
        client.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.get_waiter("table_exists").wait(TableName=TABLE_NAME)
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceInUseException":
            raise


def create_item(body: dict) -> tuple[int, dict]:
    title = str(body.get("title", "")).strip()
    if not title:
        return 400, {"error": "field 'title' is required"}
    item = {
        "id": str(uuid.uuid4()),
        "title": title[:200],
        "note": str(body.get("note", ""))[:1000],
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    _table().put_item(Item=item)
    return 201, item


def list_items() -> tuple[int, dict]:
    items = _table().scan(Limit=100).get("Items", [])
    items.sort(key=lambda i: i.get("created_at", ""))
    return 200, {"items": items, "count": len(items)}


def get_item(item_id: str) -> tuple[int, dict]:
    item = _table().get_item(Key={"id": item_id}).get("Item")
    if item is None:
        return 404, {"error": "item not found"}
    return 200, item


def delete_item(item_id: str) -> tuple[int, dict]:
    resp = _table().delete_item(Key={"id": item_id}, ReturnValues="ALL_OLD")
    if "Attributes" not in resp:
        return 404, {"error": "item not found"}
    return 200, {"deleted": item_id}


def route(method: str, path: str, raw_body: str | None) -> tuple[int, dict]:
    """Маршрутизація: (метод, шлях) -> (HTTP-статус, тіло відповіді)."""
    parts = [p for p in path.strip("/").split("/") if p]
    try:
        body = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        return 400, {"error": "invalid JSON"}

    if parts == ["health"] and method == "GET":
        return 200, {"status": "ok"}
    if parts == ["items"]:
        if method == "POST":
            return create_item(body)
        if method == "GET":
            return list_items()
        return 405, {"error": "method not allowed"}
    if len(parts) == 2 and parts[0] == "items":
        if method == "GET":
            return get_item(parts[1])
        if method == "DELETE":
            return delete_item(parts[1])
        return 405, {"error": "method not allowed"}
    return 404, {"error": "route not found"}
