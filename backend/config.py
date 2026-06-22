"""
Configuration module for backend services.
Contains application settings and configuration management.
"""
import os
from typing import Optional


class Settings:
    """Application settings class."""
    
    def __init__(self):
        self.database_url: str = os.getenv("DATABASE_URL", "sqlite:///./test.db")
        self.redis_host: str = os.getenv("REDIS_HOST", "localhost")
        self.redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_password: Optional[str] = os.getenv("REDIS_PASSWORD", None)
        self.api_key_secret: str = os.getenv("FIREAI_API_KEY", "dev-secret-key-change-in-production")
        self.debug: bool = bool(os.getenv("DEBUG", "False").lower() in ("true", "1", "yes"))
        self.environment: str = os.getenv("ENVIRONMENT", "development")


# Create a global settings instance
settings = Settings()