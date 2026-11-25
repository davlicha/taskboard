"""AWS Lambda обробник для API Gateway (REST API, proxy-інтеграція)."""

import base64
import json
import logging

from core import route

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    method = event.get("httpMethod", "GET")
    path = event.get("path", "/")
    # API Gateway у LocalStack може передавати шлях зі стейджем — прибираємо його
    stage = (event.get("requestContext") or {}).get("stage")
    if stage and path.startswith(f"/{stage}/"):
        path = path[len(stage) + 1 :]

    body = event.get("body")
    if body and event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")

    try:
        status, payload = route(method, path, body)
    except Exception:  # noqa: BLE001
        logger.exception("unhandled error")
        status, payload = 500, {"error": "internal error"}

    logger.info(json.dumps({"method": method, "path": path, "status": status}))
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload, ensure_ascii=False, default=str),
    }
