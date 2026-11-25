#!/usr/bin/env python3
"""Генератор HTTP-навантаження без зовнішніх залежностей.

Рахує розподіл відповідей між екземплярами (заголовок X-Instance-Id), частку помилок,
пропускну здатність і перцентилі затримки.

  python3 loadtest.py --url http://localhost:8080/items -n 300 -c 10
"""

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor


def one(url: str, timeout: float) -> tuple[str, int, float]:
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            r.read()
            return r.headers.get("X-Instance-Id", "?"), r.status, time.perf_counter() - start
    except urllib.error.HTTPError as e:
        return e.headers.get("X-Instance-Id", "?"), e.code, time.perf_counter() - start
    except Exception:  # noqa: BLE001
        return "connection-error", 0, time.perf_counter() - start


def run(url: str, n: int, concurrency: int, timeout: float = 10) -> dict:
    t0 = time.perf_counter()
    with ThreadPoolExecutor(concurrency) as pool:
        results = list(pool.map(lambda _: one(url, timeout), range(n)))
    total = time.perf_counter() - t0
    lat = sorted(r[2] * 1000 for r in results)
    ok = sum(1 for r in results if 200 <= r[1] < 400)
    return {
        "url": url,
        "requests": n,
        "concurrency": concurrency,
        "ok": ok,
        "errors": n - ok,
        "error_rate": round((n - ok) / n, 4),
        "duration_s": round(total, 2),
        "rps": round(n / total, 1),
        "latency_ms": {
            "avg": round(statistics.mean(lat), 1),
            "p50": round(lat[len(lat) // 2], 1),
            "p95": round(lat[int(len(lat) * 0.95) - 1], 1),
            "max": round(lat[-1], 1),
        },
        "by_instance": dict(sorted(Counter(r[0] for r in results).items())),
        "by_status": dict(sorted(Counter(str(r[1]) for r in results).items())),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="http://localhost:8080/items")
    p.add_argument("-n", "--requests", type=int, default=300)
    p.add_argument("-c", "--concurrency", type=int, default=10)
    p.add_argument("--json", action="store_true", help="лише JSON")
    a = p.parse_args()
    res = run(a.url, a.requests, a.concurrency)
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
        return
    print(f"URL: {res['url']}  n={res['requests']} c={res['concurrency']}")
    print(f"OK: {res['ok']}  errors: {res['errors']} ({res['error_rate']:.1%})  RPS: {res['rps']}")
    print(f"latency ms: {res['latency_ms']}")
    print("розподіл за екземплярами:")
    for inst, cnt in res["by_instance"].items():
        print(f"  {inst:18s} {cnt:5d}  {cnt / res['requests']:6.1%}  {'#' * round(40 * cnt / res['requests'])}")


if __name__ == "__main__":
    main()
