from typing import Optional
from urllib.parse import quote
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "RN Robots Voice Assistant"

    # ==========================================
    # FastAPI Web Service Settings
    # ==========================================
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    host: str = "0.0.0.0"
    port: int = 8000

    # ==========================================
    # Gemini AI Configuration
    # ==========================================
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # ==========================================
    # RabbitMQ Remote Broker Connection
    # ==========================================
    rabbitmq_host: Optional[str] = None
    rabbitmq_amqp_port: int = 5672
    rabbitmq_user: Optional[str] = None
    rabbitmq_password: Optional[str] = None
    rabbitmq_vhost: str = "/"
    rabbitmq_use_ssl: bool = False
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"

    # ==========================================
    # RabbitMQ Command Routing Configuration
    # ==========================================
    rabbitmq_command_exchange: str = "iot_commands"
    rabbitmq_command_queue: str = "iot_commands"
    rabbitmq_command_routing_key: str = "iot.command"

    # ==========================================
    # STT & Speech Configuration
    # ==========================================
    whisper_model: str = "base.en"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    stt_engine: str = "gemini"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @model_validator(mode="after")
    def compute_rabbitmq_url(self):
        """Construct full AMQP/AMQPS broker URL from connection parameters if host is specified."""
        if self.rabbitmq_host and self.rabbitmq_host not in ("your-rabbitmq-host", ""):
            scheme = "amqps" if self.rabbitmq_use_ssl else "amqp"
            user = quote(self.rabbitmq_user or "guest", safe="")
            pwd = quote(self.rabbitmq_password or "guest", safe="")
            vhost = self.rabbitmq_vhost.lstrip("/")
            self.rabbitmq_url = f"{scheme}://{user}:{pwd}@{self.rabbitmq_host}:{self.rabbitmq_amqp_port}/{vhost}"
        return self


settings = Settings()
