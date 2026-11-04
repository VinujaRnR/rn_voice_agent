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
    # Database Configuration (MySQL 8.4 / Async)
    # ==========================================
    database_url: Optional[str] = None
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "sarah_db"
    mysql_pool_size: int = 10
    mysql_max_overflow: int = 20
    mysql_pool_recycle: int = 3600
    app_encryption_key: str = "sarah-secret-encryption-key-32b!"

    # ==========================================
    # Authentication & JWT Configuration
    # ==========================================
    jwt_secret_key: str = "sarah-jwt-secret-key-change-in-production-min32chars!"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440  # 24 hours
    jwt_refresh_token_expire_days: int = 30
    jwt_issuer: str = "rn-robots-sarah"

    # ==========================================
    # Gemini Live & Zara Voice Configuration
    # ==========================================
    gemini_live_model: str = "gemini-3.5-flash-live-preview"
    gemini_live_fallback_model: str = "gemini-2.5-flash-native-audio-latest"
    gemini_live_voice: str = "Aoede"
    gemini_live_input_sample_rate: int = 16000
    gemini_live_output_sample_rate: int = 24000
    zara_live_ws_ticket_expire_seconds: int = 120

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
    def async_database_url(self) -> str:
        """Construct full async database URL. Defaults to MySQL with asyncmy dialect."""
        if self.database_url:
            return self.database_url
        user = quote(self.mysql_user or "root", safe="")
        pwd = quote(self.mysql_password or "", safe="")
        return f"mysql+asyncmy://{user}:{pwd}@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"

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
