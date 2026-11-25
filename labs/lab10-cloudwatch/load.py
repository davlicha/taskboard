#!/usr/bin/env python3
"""ЛР-10: контрольоване навантаження за сценаріями.

  normal  — звичайні запити
  errors  — частка запитів з ?fail=1 (керовані 5xx)
  slow    — частка запитів з ?delay_ms=N (керована затримка)
"""

import argparse
import random
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def hit(url: str) -> int:
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            r.read()
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa: BLE001
        return 0


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("scenario", choices=["normal", "errors", "slow"])
    p.add_argument("--url", default="http://localhost:8080/items")
    p.add_argument("--duration", type=int, default=60, help="секунд")
    p.add_argument("--rps", type=float, default=20)
    p.add_argument("--fraction", type=float, default=0.4, help="частка 'поганих' запитів")
    p.add_argument("--delay-ms", type=int, default=600)
    a = p.parse_args()

    stats = {"sent": 0, "5xx": 0}
    end = time.time() + a.duration
    with ThreadPoolExecutor(32) as pool:
        while time.time() < end:
            url = a.url
            if a.scenario == "errors" and random.random() < a.fraction:
                url += "?fail=1"
            elif a.scenario == "slow" and random.random() < a.fraction:
                url += f"?delay_ms={a.delay_ms}"
            fut = pool.submit(hit, url)
            fut.add_done_callback(lambda f: stats.__setitem__("5xx", stats["5xx"] + (f.result() >= 500)))
            stats["sent"] += 1
            time.sleep(1 / a.rps)
    print(f"[{a.scenario}] sent={stats['sent']} 5xx={stats['5xx']} duration={a.duration}s target_rps={a.rps}")


if __name__ == "__main__":
    main()
