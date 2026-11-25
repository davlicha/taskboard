import asyncio
import logging
import random
import time

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from starlette.routing import Match

from .config import settings
from .db import Base, Task, engine, get_session
from .logging_setup import setup_logging

log = setup_logging(settings.log_level)

REQUESTS = Counter(
    "http_requests_total",
    "Кількість HTTP-запитів",
    ["method", "route", "status"],
)
LATENCY = Histogram(
    "http_request_duration_seconds",
    "Тривалість обробки HTTP-запитів",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
)

app = FastAPI(title=settings.app_name, version=settings.app_version)


@app.on_event("startup")
def create_schema() -> None:
    # Повторні спроби: у docker compose / k8s база може стартувати пізніше
    for attempt in range(30):
        try:
            Base.metadata.create_all(engine)
            log.info("schema ready", extra={"version": settings.app_version})
            return
        except Exception:  # noqa: BLE001
            log.warning("database not ready, retry %s", attempt + 1)
            time.sleep(2)
    raise RuntimeError("database is unavailable")


def route_template(request: Request) -> str:
    """Шаблон маршруту (/api/tasks/{task_id}), а не сирий шлях — мала кардинальність міток."""
    route = request.scope.get("route")
    if route is not None:
        return route.path
    # маршрут ще не визначено (напр. помилка інжектована до виклику обробника)
    for candidate in request.app.router.routes:
        match, _ = candidate.matches(request.scope)
        if match == Match.FULL:
            return getattr(candidate, "path", "unmatched")
    return "unmatched"


@app.middleware("http")
async def observability(request: Request, call_next):
    start = time.perf_counter()
    path = request.url.path
    injected = path.startswith("/api/") and settings.fail_rate > 0 and random.random() < settings.fail_rate
    if path.startswith("/api/") and settings.slow_ms > 0:
        await asyncio.sleep(settings.slow_ms / 1000)
    if injected:
        response = JSONResponse({"detail": "injected failure (FAIL_RATE)"}, status_code=500)
    else:
        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001
            log.exception("unhandled error")
            response = JSONResponse({"detail": "internal error"}, status_code=500)
    elapsed = time.perf_counter() - start
    route = route_template(request)
    if route != "/metrics":
        REQUESTS.labels(request.method, route, str(response.status_code)).inc()
        LATENCY.labels(request.method, route).observe(elapsed)
        level = logging.ERROR if response.status_code >= 500 else logging.INFO
        log.log(
            level,
            "request",
            extra={
                "method": request.method,
                "route": route,
                "status": response.status_code,
                "duration_ms": round(elapsed * 1000, 2),
                "instance": settings.instance_id,
                "version": settings.app_version,
            },
        )
    response.headers["X-Instance"] = settings.instance_id
    response.headers["X-App-Version"] = settings.app_version
    return response


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    done: bool = False


class TaskOut(TaskIn):
    id: int


def to_out(task: Task) -> TaskOut:
    return TaskOut(id=task.id, title=task.title, done=task.done)


@app.get("/health")
def health(session: Session = Depends(get_session)):
    try:
        session.execute(text("SELECT 1"))
        db = "ok"
    except Exception:  # noqa: BLE001
        db = "down"
    body = {
        "status": "ok" if db == "ok" else "degraded",
        "db": db,
        "version": settings.app_version,
        "env": settings.app_env,
        "instance": settings.instance_id,
    }
    return JSONResponse(body, status_code=200 if db == "ok" else 503)


@app.get("/livez")
def livez():
    return {"status": "alive"}


@app.get("/version")
def version():
    return {"version": settings.app_version, "instance": settings.instance_id}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/tasks", response_model=list[TaskOut])
def list_tasks(session: Session = Depends(get_session)):
    rows = session.scalars(select(Task).order_by(Task.id)).all()
    return [to_out(t) for t in rows]


@app.post("/api/tasks", response_model=TaskOut, status_code=201)
def create_task(payload: TaskIn, session: Session = Depends(get_session)):
    task = Task(title=payload.title, done=payload.done)
    session.add(task)
    session.commit()
    return to_out(task)


@app.get("/api/tasks/{task_id}", response_model=TaskOut)
def get_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    return to_out(task)


@app.put("/api/tasks/{task_id}", response_model=TaskOut)
def update_task(task_id: int, payload: TaskIn, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    task.title, task.done = payload.title, payload.done
    session.commit()
    return to_out(task)


@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "task not found")
    session.delete(task)
    session.commit()
    return Response(status_code=204)
