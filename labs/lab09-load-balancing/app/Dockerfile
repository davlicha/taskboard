# Контекст збірки — каталог labs/ (щоб узяти core.py з ЛР-8)
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY lab09-load-balancing/app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd -u 10001 app
COPY lab08-serverless/lambda/core.py .
COPY lab09-load-balancing/app/server.py lab09-load-balancing/app/metrics.py ./
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=2s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["python", "server.py"]
