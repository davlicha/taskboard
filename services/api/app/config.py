import os
import socket


class Settings:
    """Конфігурація застосунку з оточення (ConfigMap / Secret у Kubernetes)."""

    def __init__(self) -> None:
        self.app_name = os.getenv("APP_NAME", "taskboard-api")
        self.app_env = os.getenv("APP_ENV", "dev")
        self.app_version = os.getenv("APP_VERSION", "dev")
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.database_url = os.getenv("DATABASE_URL", "sqlite:///./taskboard.db")
        self.fail_rate = float(os.getenv("FAIL_RATE", "0") or 0)
        self.slow_ms = int(os.getenv("SLOW_MS", "0") or 0)
        self.instance_id = os.getenv("INSTANCE_ID", socket.gethostname())


settings = Settings()
