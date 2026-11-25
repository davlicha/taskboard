"""Контейнерна версія застосунку з ЛР-8 (ЛР-9, ЛР-10).

Та сама бізнес-логіка (core.py) + DynamoDB у LocalStack, але як HTTP-сервер у контейнері.
Кожен екземпляр повертає власний ідентифікатор (INSTANCE_ID) у тілі та заголовку X-Instance-Id.
"""

import json
import logging
import os
import random
import socket
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import core
from metrics import MetricsPublisher

INSTANCE_ID = os.getenv("INSTANCE_ID", socket.gethostname())
PORT = int(os.getenv("PORT", "8000"))
WORK_MS = int(os.getenv("WORK_MS", "20"))  # імітація обробки запиту
FAIL_RATE = float(os.getenv("FAIL_RATE", "0"))

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("app")
metrics = MetricsPublisher.from_env(INSTANCE_ID)


class Handler(BaseHTTPRequestHandler):
    server_version = "items-app/1.0"

    def log_message(self, *args):  # власне JSON-логування нижче
        pass

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Instance-Id", INSTANCE_ID)
        self.end_headers()
        self.wfile.write(body)

    def _handle(self) -> None:
        start = time.perf_counter()
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode() if length else None

        if url.path == "/health":
            status, payload = 200, {"status": "ok", "instance": INSTANCE_ID}
        elif url.path == "/":
            status, payload = 200, {"instance": INSTANCE_ID, "message": "items app behind nginx"}
        else:
            # Керовані "збої" для ЛР-10: ?fail=1 -> 500, ?delay_ms=N -> затримка
            delay = int(query.get("delay_ms", ["0"])[0])
            if delay:
                time.sleep(min(delay, 10_000) / 1000)
            if WORK_MS:
                time.sleep(WORK_MS / 1000)
            if query.get("fail", ["0"])[0] == "1" or random.random() < FAIL_RATE:
                status, payload = 500, {"error": "simulated failure"}
            else:
                try:
                    status, payload = core.route(self.command, url.path, raw)
                except Exception:  # noqa: BLE001
                    log.exception("unhandled")
                    status, payload = 500, {"error": "internal error"}
            payload = {**payload, "instance": INSTANCE_ID} if isinstance(payload, dict) else payload

        self._send(status, payload)
        elapsed_ms = (time.perf_counter() - start) * 1000
        if url.path != "/health":
            metrics.record(status, elapsed_ms)
        log.info(
            json.dumps(
                {"instance": INSTANCE_ID, "method": self.command, "path": url.path, "status": status,
                 "ms": round(elapsed_ms, 1)}
            )
        )

    do_GET = do_POST = do_DELETE = _handle


def main() -> None:
    for attempt in range(30):
        try:
            core.ensure_table()
            break
        except Exception as exc:  # noqa: BLE001
            log.info(f"waiting for DynamoDB ({attempt + 1}): {exc.__class__.__name__}")
            time.sleep(2)
    metrics.start()
    # Однопотоковий сервер: один екземпляр обробляє один запит за раз —
    # тому масштабування на кілька екземплярів дає помітний приріст пропускної здатності.
    log.info(json.dumps({"instance": INSTANCE_ID, "msg": f"listening on :{PORT}"}))
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
