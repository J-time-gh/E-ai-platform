from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置：从环境变量 / .env 文件读取，类型安全。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Enterprise AI Platform"
    app_version: str = "0.1.0"
    environment: str = "development"
    log_level: str = "INFO"

    database_url: str
    test_database_url: str
    redis_url: str

    upload_dir: str = "data/uploads"
    embedding_model: str = "BAAI/bge-m3"
    llm_base_url: str = "http://127.0.0.1:1234/v1"
    llm_model: str = "qwen2.5-14b-instruct"
    llm_api_key: str = "lm-studio"

    llm_timeout: float = 120.0
    llm_temperature: float = 0.2

    embedding_device: str = "cuda"
    embedding_batch_size: int = 32
    hf_endpoint: str = "https://hf-mirror.com"
    hf_home: str = "D:/Tool/Cache/huggingface"


settings = Settings()
