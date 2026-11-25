import os
import socket

import requests
from flask import Flask, redirect, render_template, request, url_for

API_URL = os.getenv("API_URL", "http://localhost:8000")
APP_VERSION = os.getenv("APP_VERSION", "dev")
APP_TITLE = os.getenv("APP_TITLE", "Taskboard")
TIMEOUT = float(os.getenv("API_TIMEOUT", "3"))

app = Flask(__name__)


def api(method: str, path: str, **kwargs):
    return requests.request(method, f"{API_URL}{path}", timeout=TIMEOUT, **kwargs)


@app.get("/")
def index():
    error = None
    tasks, api_info = [], {}
    try:
        tasks = api("GET", "/api/tasks").json()
        api_info = api("GET", "/version").json()
    except requests.RequestException as exc:
        error = f"API недоступний: {exc.__class__.__name__}"
    return render_template(
        "index.html",
        title=APP_TITLE,
        tasks=tasks,
        error=error,
        web_version=APP_VERSION,
        api_info=api_info,
        host=socket.gethostname(),
    )


@app.post("/tasks")
def create():
    title = request.form.get("title", "").strip()
    if title:
        api("POST", "/api/tasks", json={"title": title})
    return redirect(url_for("index"))


@app.post("/tasks/<int:task_id>/toggle")
def toggle(task_id: int):
    task = api("GET", f"/api/tasks/{task_id}").json()
    api("PUT", f"/api/tasks/{task_id}", json={"title": task["title"], "done": not task["done"]})
    return redirect(url_for("index"))


@app.post("/tasks/<int:task_id>/delete")
def delete(task_id: int):
    api("DELETE", f"/api/tasks/{task_id}")
    return redirect(url_for("index"))


@app.get("/health")
def health():
    return {"status": "ok", "version": APP_VERSION}
