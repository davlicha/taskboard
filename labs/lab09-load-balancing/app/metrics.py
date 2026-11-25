"""ЛР-10: збір і публікація власних метрик у CloudWatch (PutMetricData).

Метрики накопичуються в пам'яті й відправляються пакетом кожні FLUSH_SECONDS:
  RequestCount (Count), ErrorCount (Count, статус >= 500), Latency (Milliseconds, StatisticSet)
"""

import logging
import os
import threading
import time

import boto3

log = logging.getLogger("metrics")


class MetricsPublisher:
    def __init__(self, enabled: bool, namespace: str, service: str, instance: str, flush_seconds: float):
        self.enabled = enabled
        self.namespace = namespace
        self.service = service
        self.instance = instance
        self.flush_seconds = flush_seconds
        self._lock = threading.Lock()
        self._reset()

    @classmethod
    def from_env(cls, instance: str) -> "MetricsPublisher":
        return cls(
            enabled=os.getenv("METRICS_ENABLED", "false").lower() == "true",
            namespace=os.getenv("METRICS_NAMESPACE", "Lab10/ItemsApp"),
            service=os.getenv("SERVICE_NAME", "items-api"),
            instance=instance,
            flush_seconds=float(os.getenv("FLUSH_SECONDS", "10")),
        )

    def _reset(self) -> None:
        self.count = self.errors = 0
        self.lat_sum = 0.0
        self.lat_min = float("inf")
        self.lat_max = 0.0

    def record(self, status: int, latency_ms: float) -> None:
        if not self.enabled:
            return
        with self._lock:
            self.count += 1
            self.errors += status >= 500
            self.lat_sum += latency_ms
            self.lat_min = min(self.lat_min, latency_ms)
            self.lat_max = max(self.lat_max, latency_ms)

    def snapshot(self) -> list[dict]:
        with self._lock:
            if self.count == 0:
                return []
            count, errors = self.count, self.errors
            stats = {"SampleCount": count, "Sum": self.lat_sum, "Minimum": self.lat_min, "Maximum": self.lat_max}
            self._reset()
        # Один набір вимірів (Service): метрики всіх екземплярів агрегуються в один ряд.
        # (LocalStack підсумовує ряди з додатковими вимірами в запиті за Service — тому Instance не додаємо.)
        dims = [{"Name": "Service", "Value": self.service}]
        return [
            {"MetricName": "RequestCount", "Dimensions": dims, "Value": count, "Unit": "Count"},
            {"MetricName": "ErrorCount", "Dimensions": dims, "Value": errors, "Unit": "Count"},
            {"MetricName": "Latency", "Dimensions": dims, "StatisticValues": stats, "Unit": "Milliseconds"},
        ]

    def flush(self, client) -> None:
        data = self.snapshot()
        if data:
            client.put_metric_data(Namespace=self.namespace, MetricData=data)

    def start(self) -> None:
        if not self.enabled:
            return
        client = boto3.client("cloudwatch")

        def loop():
            while True:
                time.sleep(self.flush_seconds)
                try:
                    self.flush(client)
                except Exception as exc:  # noqa: BLE001
                    log.warning(f"PutMetricData failed: {exc}")

        threading.Thread(target=loop, daemon=True, name="metrics").start()
