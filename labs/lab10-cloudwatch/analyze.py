#!/usr/bin/env python3
"""ЛР-10: отримання метрик (GetMetricData + GetMetricStatistics), розрахунок показників і графіки.

  python3 analyze.py --minutes 15 --period 30
Результат: out/metrics.csv, out/metrics.png, out/summary.md
"""

import argparse
import csv
import json
import os
from datetime import UTC, datetime, timedelta

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from common import DIMS, NAMESPACE, cloudwatch  # noqa: E402


def query(metric: str, stat: str, qid: str, period: int) -> dict:
    return {
        "Id": qid,
        "MetricStat": {
            "Metric": {"Namespace": NAMESPACE, "MetricName": metric, "Dimensions": DIMS},
            "Period": period,
            "Stat": stat,
        },
        "ReturnData": True,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--minutes", type=int, default=15)
    p.add_argument("--period", type=int, default=30)
    p.add_argument("--events", default="out/events.json", help="позначки сценаріїв для графіка")
    a = p.parse_args()
    os.makedirs("out", exist_ok=True)

    cw = cloudwatch()
    end = datetime.now(UTC)
    start = end - timedelta(minutes=a.minutes)

    # --- GetMetricData: кілька рядів одним запитом
    resp = cw.get_metric_data(
        MetricDataQueries=[
            query("RequestCount", "Sum", "req", a.period),
            query("ErrorCount", "Sum", "err", a.period),
            query("Latency", "Average", "lat", a.period),
            query("Latency", "Maximum", "latmax", a.period),
        ],
        StartTime=start,
        EndTime=end,
        ScanBy="TimestampAscending",
    )
    series = {r["Id"]: dict(zip(r["Timestamps"], r["Values"], strict=True)) for r in resp["MetricDataResults"]}
    times = sorted(series["req"])

    rows = []
    for t in times:
        req = series["req"].get(t, 0)
        err = series["err"].get(t, 0)
        rows.append(
            {
                "time": t.astimezone(UTC).strftime("%H:%M:%S"),
                "requests": int(req),
                "rps": round(req / a.period, 2),
                "errors": int(err),
                "error_rate_pct": round(100 * err / req, 2) if req else 0,
                "avg_latency_ms": round(series["lat"].get(t, 0), 1),
                "max_latency_ms": round(series["latmax"].get(t, 0), 1),
            }
        )
    with open("out/metrics.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["time"])
        w.writeheader()
        w.writerows(rows)

    # --- GetMetricStatistics: агрегат за весь інтервал
    def total(metric: str, stat: str) -> float:
        dps = cw.get_metric_statistics(
            Namespace=NAMESPACE,
            MetricName=metric,
            Dimensions=DIMS,
            StartTime=start,
            EndTime=end,
            Period=a.minutes * 60,
            Statistics=[stat],
        )["Datapoints"]
        return sum(dp[stat] for dp in dps) if stat == "Sum" else (dps[0][stat] if dps else 0.0)

    total_req = total("RequestCount", "Sum")
    total_err = total("ErrorCount", "Sum")
    lat_stats = cw.get_metric_statistics(
        Namespace=NAMESPACE, MetricName="Latency", Dimensions=DIMS, StartTime=start, EndTime=end,
        Period=a.minutes * 60, Statistics=["SampleCount", "Sum", "Maximum"],
    )["Datapoints"]
    lat_n = sum(d["SampleCount"] for d in lat_stats)
    avg_lat = sum(d["Sum"] for d in lat_stats) / lat_n if lat_n else 0
    max_lat = max((d["Maximum"] for d in lat_stats), default=0)

    alarms = cw.describe_alarms()["MetricAlarms"]
    # Переходи станів alarm, записані run_experiment.sh (опитування describe-alarms кожні 5 с)
    transitions, last = [], {}
    if os.path.exists("out/alarm_states.csv"):
        with open("out/alarm_states.csv") as f:
            for row in csv.DictReader(f):
                if last.get(row["alarm"]) != row["state"]:
                    transitions.append(row)
                    last[row["alarm"]] = row["state"]

    # --- графіки
    events = json.load(open(a.events)) if os.path.exists(a.events) else []
    if times:
        fig, ax = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
        ax[0].plot(times, [r["rps"] for r in rows], marker="o", color="#2a6fdb")
        ax[0].set_ylabel("запитів/с")
        ax[0].set_title("Кількість запитів (RequestCount / період)")
        ax[1].plot(times, [r["error_rate_pct"] for r in rows], marker="o", color="#d64545")
        ax[1].axhline(5, ls="--", color="gray", lw=1)
        ax[1].set_ylabel("% помилок")
        ax[1].set_title("Частка помилок 5xx")
        ax[2].plot(times, [r["avg_latency_ms"] for r in rows], marker="o", color="#2e9e6a", label="середня")
        ax[2].plot(times, [r["max_latency_ms"] for r in rows], ls=":", color="#2e9e6a", label="максимальна")
        ax[2].axhline(300, ls="--", color="gray", lw=1, label="поріг alarm 300 мс")
        ax[2].set_ylabel("мс")
        ax[2].set_title("Час відповіді (Latency)")
        ax[2].legend(loc="upper left")
        for t in transitions:
            if t["state"] == "ALARM":
                idx = 1 if "errors" in t["alarm"] else 2
                ax[idx].axvline(datetime.fromisoformat(t["time"].replace("Z", "+00:00")), color="red", lw=1.5, ls="-.")
        for e in events:
            ts = datetime.fromisoformat(e["start"])
            for axis in ax:
                axis.axvline(ts, color="#999", lw=0.8)
            ax[0].annotate(e["name"], (ts, ax[0].get_ylim()[1]), fontsize=8, va="top", rotation=90)
        ax[2].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=UTC))
        for axis in ax:
            axis.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig("out/metrics.png", dpi=120)

    with open("out/summary.md", "w") as f:
        f.write(f"# Підсумок метрик ({start:%H:%M}–{end:%H:%M} UTC, період {a.period} с)\n\n")
        f.write(f"- Запитів за інтервал: **{int(total_req)}** (~{total_req / (a.minutes * 60):.1f} запит/с)\n")
        f.write(f"- Помилок 5xx: **{int(total_err)}** ({100 * total_err / total_req if total_req else 0:.1f}%)\n")
        f.write(f"- Середній час відповіді: **{avg_lat:.1f} мс**, максимальний: {max_lat:.1f} мс\n\n")
        f.write("| час | запитів | RPS | помилок | % помилок | сер. мс | макс. мс |\n|---|---|---|---|---|---|---|\n")
        for r in rows:
            f.write("| " + " | ".join(str(v) for v in r.values()) + " |\n")
        f.write("\n## Alarms\n\n| alarm | стан | причина |\n|---|---|---|\n")
        for al in alarms:
            f.write(f"| {al['AlarmName']} | {al['StateValue']} | {al.get('StateReason', '')[:120]} |\n")
        f.write("\n## Переходи станів alarm (опитування кожні 5 с)\n\n")
        for t in transitions:
            f.write(f"- {t['time'][11:19]} UTC — {t['alarm']} → **{t['state']}**\n")
        if events:
            f.write("\n## Сценарії навантаження\n\n")
            for e in events:
                f.write(f"- {e['start'][11:19]} UTC — {e['name']}\n")
    print(open("out/summary.md").read())


if __name__ == "__main__":
    main()
