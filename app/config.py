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
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_thinking_budget: int = 1024
    gemini_reasoning_enabled: bool = True
    gemini_temperature: float = 0.2

    # ==========================================
    # RabbitMQ Remote Broker Connection
    # ==========================================
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    rabbitmq_host: Optional[str] = None
    rabbitmq_amqp_port: int = 5672
    rabbitmq_user: Optional[str] = None
    rabbitmq_password: Optional[str] = None
    rabbitmq_vhost: str = "/"
    rabbitmq_use_ssl: bool = False
    rabbitmq_timeout_seconds: int = 15

    # ==========================================
    # RabbitMQ Command Routing Configuration
    # ==========================================
    rabbitmq_command_exchange: str = "iot_commands"
    rabbitmq_command_queue: str = "iot_exchange"
    rabbitmq_command_routing_key: str = "iot.command"
    rabbitmq_deadletter_exchange: str = "iot.deadletter"
    rabbitmq_deadletter_queue: str = "iot_exchange.deadletter"
    rabbitmq_result_exchange: str = "iot_commands"
    rabbitmq_result_queue: str = "results"
    rabbitmq_result_routing_key: str = "results"

    # ==========================================
    # Device Registry Data Table Configuration
    # ==========================================
    devices_data_file: str = "data/devices.json"

    # ==========================================
    # STT & Speech Configuration
    # ==========================================
    whisper_model: str = "base.en"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_beam_size: int = 5
    whisper_initial_prompt: str = (
        "Sarah, turn on testing farm lights, room lights, kitchen lights, desk lamp, "
        "thermostat, Colombo, Sri Lanka, weather, temperature, schedule, status."
    )
    audio_preprocess_enabled: bool = True
    audio_target_peak: float = 0.90
    audio_noise_reduction_enabled: bool = True
    audio_silence_trim_enabled: bool = True
    stt_engine: str = "gemini"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def is_placeholder_broker(self) -> bool:
        """Check if broker URL contains unpopulated template values."""
        raw_url = (self.rabbitmq_url or "").lower()
        placeholders = [
            "broker_host",
            "your-rabbitmq-host",
            "user:password@broker_host",
            "your-rabbitmq-user"
        ]
        return any(p in raw_url for p in placeholders)

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
