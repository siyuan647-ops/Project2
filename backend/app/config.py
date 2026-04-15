"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # LLM (Kimi K2.5 via OpenAI-compatible API)
    KIMI_API_KEY: str = ""
    KIMI_BASE_URL: str = "https://api.moonshot.cn/v1"
    KIMI_MODEL_NAME: str = "kimi-k2.5"

    # Tavily Search API (optional - falls back to DuckDuckGo if not set)
    TAVILY_API_KEY: str = ""

    # Polygon.io (optional - when set, stock_data tools use Polygon instead of yfinance for US equities)
    POLYGON_API_KEY: str = ""

    # Application
    APP_TITLE: str = "Multi-Agent Financial Decision Platform"
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:3000", "http://localhost"]

    # File storage
    UPLOAD_DIR: Path = Path(__file__).resolve().parent.parent / "uploads"
    OUTPUT_DIR: Path = Path(__file__).resolve().parent.parent / "outputs"

    # PostgreSQL database
    DATABASE_URL: str = "postgresql://finapp:finapp_secret@localhost:5432/financial_platform"

    # ML model
    MODEL_DIR: Path = Path(__file__).resolve().parent / "ml" / "model"

    # Routing
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"
    VECTOR_DIMENSIONS: int = 384

    # Security
    API_KEY: str = ""  # Set via env; empty = skip auth (dev mode)
    RATE_LIMIT_ADVISOR: str = "10/minute"
    RATE_LIMIT_CREDIT: str = "20/minute"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()

# Ensure directories exist
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
settings.MODEL_DIR.mkdir(parents=True, exist_ok=True)
